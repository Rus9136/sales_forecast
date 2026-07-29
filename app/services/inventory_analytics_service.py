"""Аналитика складского контура: что списываем, почему и сколько это стоит.

Три среза:
  * ``writeoff_summary``   — склад × причина: где и на что уходят деньги
  * ``writeoff_by_product``— топ позиций с долей потерь от поставки
  * ``supply_loop``        — петля «поставлено → продано → списано» по SKU,
                             база для рекомендации заявки

Правила, зашитые в запросы:
  * ``writeoff_document.status = 'PROCESSED'`` — DELETED-документов в сети ~25%
  * ``SUM(writeoff_item.cost)`` без домножения на amount — cost уже за строку
  * ``incoming_invoice_item.is_additional_expense`` исключается из количеств:
    это доставка и прочие услуги, а не товар
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings

logger = logging.getLogger(__name__)


def _revenue_column() -> str:
    """Колонка выручки в базе, выбранной флагом REVENUE_BASIS."""
    return "ri.paid_sum" if settings.REVENUE_BASIS == "paid" else "ri.dish_sum"


class InventoryAnalyticsService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Списания: склад × причина
    # ------------------------------------------------------------------

    def writeoff_summary(
        self, department_id: str, from_date: date, to_date: date,
    ) -> Dict[str, Any]:
        rows = self.db.execute(
            text("""
                SELECT
                    d.store_id::text                AS store_id,
                    COALESCE(s.name, 'Склад не определён') AS store_name,
                    d.account_id::text              AS reason_id,
                    COALESCE(a.name, 'Причина не указана') AS reason,
                    COUNT(DISTINCT d.id)            AS documents,
                    COUNT(i.id)                     AS positions,
                    COALESCE(SUM(i.cost), 0)        AS cost
                FROM writeoff_document d
                JOIN writeoff_item i ON i.document_id = d.id
                LEFT JOIN store s ON s.id = d.store_id
                LEFT JOIN iiko_account a ON a.id = d.account_id
                WHERE d.department_id = :dept ::uuid
                  AND d.status = 'PROCESSED'
                  AND d.doc_date BETWEEN :from_date AND :to_date
                GROUP BY 1, 2, 3, 4
                ORDER BY cost DESC
            """),
            {"dept": department_id, "from_date": from_date, "to_date": to_date},
        ).fetchall()

        items = [{
            "store_id": r.store_id,
            "store_name": r.store_name,
            "reason_id": r.reason_id,
            "reason": r.reason,
            "documents": r.documents,
            "positions": r.positions,
            "cost": float(r.cost),
        } for r in rows]

        total_cost = sum(i["cost"] for i in items)
        for i in items:
            i["share_of_total"] = round(i["cost"] / total_cost, 4) if total_cost else 0.0

        context = self._period_context(department_id, from_date, to_date)
        return {
            "department_id": department_id,
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "total_writeoff_cost": round(total_cost, 2),
            "revenue": context["revenue"],
            "supply_cost": context["supply_cost"],
            "writeoff_share_of_revenue": (
                round(total_cost / context["revenue"], 4) if context["revenue"] else None
            ),
            "writeoff_share_of_supply": (
                round(total_cost / context["supply_cost"], 4) if context["supply_cost"] else None
            ),
            "revenue_basis": settings.REVENUE_BASIS,
            "breakdown": items,
        }

    def _period_context(self, department_id: str, from_date: date, to_date: date) -> Dict[str, float]:
        revenue = self.db.execute(
            text(f"""
                SELECT COALESCE(SUM({_revenue_column()}), 0)
                FROM receipt_item ri
                JOIN receipt r ON r.id = ri.receipt_id AND r.open_date = ri.open_date
                WHERE r.department_id = :dept ::uuid
                  AND r.open_date BETWEEN :from_date AND :to_date
            """),
            {"dept": department_id, "from_date": from_date, "to_date": to_date},
        ).scalar() or 0

        supply = self.db.execute(
            text("""
                SELECT COALESCE(SUM(ii.line_sum), 0)
                FROM incoming_invoice_item ii
                JOIN incoming_invoice v ON v.id = ii.invoice_id
                WHERE ii.department_id = :dept ::uuid
                  AND v.status = 'PROCESSED'
                  AND ii.doc_date BETWEEN :from_date AND :to_date
            """),
            {"dept": department_id, "from_date": from_date, "to_date": to_date},
        ).scalar() or 0

        return {"revenue": float(revenue), "supply_cost": float(supply)}

    # ------------------------------------------------------------------
    # Списания: топ позиций
    # ------------------------------------------------------------------

    def writeoff_by_product(
        self, department_id: str, from_date: date, to_date: date,
        store_id: Optional[str] = None, reason_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        rows = self.db.execute(
            text("""
                WITH wo AS (
                    SELECT i.product_id,
                           SUM(i.amount) AS amount,
                           SUM(i.cost)   AS cost,
                           COUNT(DISTINCT d.id) AS documents,
                           COUNT(DISTINCT d.doc_date) AS days,
                           ARRAY_AGG(DISTINCT COALESCE(a.name, 'Не указана')) AS reasons
                    FROM writeoff_document d
                    JOIN writeoff_item i ON i.document_id = d.id
                    LEFT JOIN iiko_account a ON a.id = d.account_id
                    WHERE d.department_id = :dept ::uuid
                      AND d.status = 'PROCESSED'
                      AND d.doc_date BETWEEN :from_date AND :to_date
                      AND (:store_id ::uuid IS NULL OR d.store_id = :store_id ::uuid)
                      AND (:reason_id ::uuid IS NULL OR d.account_id = :reason_id ::uuid)
                    GROUP BY i.product_id
                ),
                sup AS (
                    SELECT ii.product_id,
                           SUM(ii.amount)   AS amount,
                           SUM(ii.line_sum) AS line_sum
                    FROM incoming_invoice_item ii
                    JOIN incoming_invoice v ON v.id = ii.invoice_id
                    WHERE ii.department_id = :dept ::uuid
                      AND v.status = 'PROCESSED'
                      AND ii.is_additional_expense = FALSE
                      AND ii.doc_date BETWEEN :from_date AND :to_date
                    GROUP BY ii.product_id
                )
                SELECT p.id            AS product_id,
                       p.name          AS product_name,
                       p.type          AS product_type,
                       mu.name         AS unit,
                       wo.amount, wo.cost, wo.documents, wo.days, wo.reasons,
                       sup.amount      AS supplied_amount,
                       sup.line_sum    AS supplied_sum
                FROM wo
                JOIN product p ON p.id = wo.product_id
                LEFT JOIN measure_unit mu ON mu.id = p.measure_unit_id
                LEFT JOIN sup ON sup.product_id = wo.product_id
                ORDER BY wo.cost DESC NULLS LAST
                LIMIT :limit
            """),
            {
                "dept": department_id, "from_date": from_date, "to_date": to_date,
                "store_id": store_id, "reason_id": reason_id, "limit": limit,
            },
        ).fetchall()

        out: List[Dict[str, Any]] = []
        for r in rows:
            supplied = float(r.supplied_amount) if r.supplied_amount is not None else None
            written = float(r.amount or 0)
            out.append({
                "product_id": r.product_id,
                "product_name": r.product_name,
                "product_type": r.product_type,
                "unit": r.unit,
                "written_amount": written,
                "written_cost": float(r.cost or 0),
                "documents": r.documents,
                "days_with_writeoff": r.days,
                "reasons": list(r.reasons or []),
                "supplied_amount": supplied,
                "supplied_sum": float(r.supplied_sum) if r.supplied_sum is not None else None,
                # Доля потерь считается только когда поставка есть: иначе позиция
                # пришла раньше периода и знаменатель был бы ложным.
                "loss_rate": round(written / supplied, 4) if supplied else None,
            })
        return out

    # ------------------------------------------------------------------
    # Динамика по неделям
    # ------------------------------------------------------------------

    def writeoff_trend(
        self, department_id: str, from_date: date, to_date: date,
    ) -> List[Dict[str, Any]]:
        rows = self.db.execute(
            text(f"""
                WITH wo AS (
                    SELECT DATE_TRUNC('week', d.doc_date)::date AS week,
                           SUM(i.cost) AS cost
                    FROM writeoff_document d
                    JOIN writeoff_item i ON i.document_id = d.id
                    WHERE d.department_id = :dept ::uuid
                      AND d.status = 'PROCESSED'
                      AND d.doc_date BETWEEN :from_date AND :to_date
                    GROUP BY 1
                ),
                rev AS (
                    SELECT DATE_TRUNC('week', r.open_date)::date AS week,
                           SUM({_revenue_column()}) AS revenue
                    FROM receipt_item ri
                    JOIN receipt r ON r.id = ri.receipt_id AND r.open_date = ri.open_date
                    WHERE r.department_id = :dept ::uuid
                      AND r.open_date BETWEEN :from_date AND :to_date
                    GROUP BY 1
                )
                SELECT COALESCE(wo.week, rev.week) AS week,
                       COALESCE(wo.cost, 0)        AS cost,
                       COALESCE(rev.revenue, 0)    AS revenue
                FROM wo FULL OUTER JOIN rev ON rev.week = wo.week
                ORDER BY 1
            """),
            {"dept": department_id, "from_date": from_date, "to_date": to_date},
        ).fetchall()

        return [{
            "week": r.week.isoformat(),
            "writeoff_cost": float(r.cost),
            "revenue": float(r.revenue),
            "share_of_revenue": round(float(r.cost) / float(r.revenue), 4) if r.revenue else None,
        } for r in rows]

    # ------------------------------------------------------------------
    # Петля «поставлено → продано → списано»
    # ------------------------------------------------------------------

    def supply_loop(
        self, department_id: str, from_date: date, to_date: date,
        supplier_id: Optional[str] = None, limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """По каждому SKU: сколько привезли, продали и списали за период.

        Нулевые продажи при ненулевой поставке — нормальная ситуация для
        заготовок и полуфабрикатов: они расходуются по техкартам, а не
        продаются напрямую. Признак ``is_resale`` это разделяет.
        """
        rows = self.db.execute(
            text(f"""
                WITH sup AS (
                    SELECT ii.product_id,
                           SUM(ii.amount)    AS amount,
                           SUM(ii.line_sum)  AS line_sum,
                           COUNT(DISTINCT ii.doc_date) AS days,
                           MAX(ii.doc_date)  AS last_date,
                           AVG(NULLIF(ii.price, 0)) AS avg_price
                    FROM incoming_invoice_item ii
                    JOIN incoming_invoice v ON v.id = ii.invoice_id
                    WHERE ii.department_id = :dept ::uuid
                      AND v.status = 'PROCESSED'
                      AND ii.is_additional_expense = FALSE
                      AND ii.doc_date BETWEEN :from_date AND :to_date
                      AND (:supplier_id ::uuid IS NULL OR v.supplier_id = :supplier_id ::uuid)
                    GROUP BY ii.product_id
                ),
                sold AS (
                    SELECT ri.product_id,
                           SUM(ri.qty)             AS qty,
                           SUM({_revenue_column()}) AS revenue,
                           SUM(ri.cost_price)      AS cost,
                           COUNT(DISTINCT r.open_date) AS days
                    FROM receipt_item ri
                    JOIN receipt r ON r.id = ri.receipt_id AND r.open_date = ri.open_date
                    WHERE r.department_id = :dept ::uuid
                      AND r.open_date BETWEEN :from_date AND :to_date
                    GROUP BY ri.product_id
                ),
                wo AS (
                    SELECT i.product_id,
                           SUM(i.amount) AS amount,
                           SUM(i.cost)   AS cost
                    FROM writeoff_document d
                    JOIN writeoff_item i ON i.document_id = d.id
                    WHERE d.department_id = :dept ::uuid
                      AND d.status = 'PROCESSED'
                      AND d.doc_date BETWEEN :from_date AND :to_date
                    GROUP BY i.product_id
                )
                SELECT p.id AS product_id, p.name AS product_name, p.type AS product_type,
                       mu.name AS unit,
                       sup.amount AS supplied_amount, sup.line_sum AS supplied_sum,
                       sup.days AS supply_days, sup.last_date AS last_supply_date,
                       sup.avg_price AS avg_purchase_price,
                       sold.qty AS sold_qty, sold.revenue AS revenue,
                       sold.cost AS sold_cost, sold.days AS sale_days,
                       wo.amount AS written_amount, wo.cost AS written_cost
                FROM sup
                JOIN product p ON p.id = sup.product_id
                LEFT JOIN measure_unit mu ON mu.id = p.measure_unit_id
                LEFT JOIN sold ON sold.product_id = sup.product_id
                LEFT JOIN wo   ON wo.product_id   = sup.product_id
                ORDER BY sup.line_sum DESC NULLS LAST
                LIMIT :limit
            """),
            {
                "dept": department_id, "from_date": from_date, "to_date": to_date,
                "supplier_id": supplier_id, "limit": limit,
            },
        ).fetchall()

        out: List[Dict[str, Any]] = []
        for r in rows:
            supplied = float(r.supplied_amount or 0)
            sold = float(r.sold_qty or 0)
            written = float(r.written_amount or 0)
            out.append({
                "product_id": r.product_id,
                "product_name": r.product_name,
                "product_type": r.product_type,
                "unit": r.unit,
                "supplied_amount": supplied,
                "supplied_sum": float(r.supplied_sum or 0),
                "supply_days": r.supply_days or 0,
                "last_supply_date": r.last_supply_date.isoformat() if r.last_supply_date else None,
                "avg_purchase_price": float(r.avg_purchase_price) if r.avg_purchase_price else None,
                "sold_qty": sold,
                "sale_days": r.sale_days or 0,
                "revenue": float(r.revenue or 0),
                "sold_cost": float(r.sold_cost or 0),
                "written_amount": written,
                "written_cost": float(r.written_cost or 0),
                "loss_rate": round(written / supplied, 4) if supplied else None,
                # Позиция перепродаётся как есть, а не расходуется по техкарте
                "is_resale": sold > 0,
            })
        return out

    # ------------------------------------------------------------------
    # Поставщики
    # ------------------------------------------------------------------

    def suppliers_of_department(
        self, department_id: str, from_date: date, to_date: date,
    ) -> List[Dict[str, Any]]:
        rows = self.db.execute(
            text("""
                SELECT v.supplier_id::text AS supplier_id,
                       COALESCE(sp.name, 'Поставщик не определён') AS supplier_name,
                       COUNT(DISTINCT v.id) AS invoices,
                       COUNT(ii.id)         AS positions,
                       SUM(ii.line_sum)     AS total_sum,
                       BOOL_OR(v.linked_outgoing_invoice_id IS NOT NULL) AS is_internal
                FROM incoming_invoice_item ii
                JOIN incoming_invoice v ON v.id = ii.invoice_id
                LEFT JOIN supplier sp ON sp.id = v.supplier_id
                WHERE ii.department_id = :dept ::uuid
                  AND v.status = 'PROCESSED'
                  AND ii.doc_date BETWEEN :from_date AND :to_date
                GROUP BY 1, 2
                ORDER BY total_sum DESC
            """),
            {"dept": department_id, "from_date": from_date, "to_date": to_date},
        ).fetchall()

        return [{
            "supplier_id": r.supplier_id,
            "supplier_name": r.supplier_name,
            "invoices": r.invoices,
            "positions": r.positions,
            "total_sum": float(r.total_sum or 0),
            "is_internal": bool(r.is_internal),
        } for r in rows]
