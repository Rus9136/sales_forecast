"""Приказы об изменении цен: сборка из утверждённых рекомендаций, отправка
в iiko, отмена, сверка статуса.

Один приказ = одна точка × одна дата вступления в силу. Так ведут приказы
руками в бэк-офисе, и так же считается эффект пачки решений
(`price_outcome_batch` по department_id × applied_at).

Что здесь ОБЯЗАТЕЛЬНО и почему:

* `deletePreviousMenu` — жёсткий `False`, не параметр и не поле API. `true`
  исключил бы из меню точки всё, чего нет в документе.
* Ревалидация каждой позиции ПЕРЕД отправкой. Между approve и отправкой цену
  могли поменять руками в iiko — тогда базис решения устарел, и позиция
  выпадает из приказа с причиной, а не уезжает вслепую.
* Атрибуты позиции (`dishOfDay`, `flyerProgram`, ценовые категории) переносятся
  из действующего приказа этой позиции, а не заполняются пустыми значениями:
  приказ задаёт позицию целиком, и пустой payload затёр бы их.
* POST в iiko не ретраится (см. iiko_menu_change_writer). При обрыве приказ
  остаётся в статусе 'sending', а документ-сирота ищется по маркеру
  `SF#{order_id}` в комментарии.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from .iiko_menu_change_writer import (
    IikoMenuChangeWriter, IikoOrderError, base_url_for_host, marker_for,
)
from .pricing_audit import log_audit

logger = logging.getLogger(__name__)

# Согласовано с APPROVED_TTL_DAYS оптимизатора: approved старше окна
# детекции считается протухшим и в приказ не идёт.
APPROVED_TTL_DAYS = 30
PRICE_MATCH_TOLERANCE = 0.01
IIKO_DATE_TO_INFINITY = "2500-01-01"


class PriceOrderError(Exception):
    """Ошибка бизнес-правил приказа. code транслируется роутером в HTTP-статус."""

    def __init__(self, code: str, message: str, http_status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def _f(value) -> Optional[float]:
    return float(value) if value is not None else None


class PriceOrderService:
    def __init__(self, db: Session):
        self.db = db
        self._rules = None

    @property
    def rules(self):
        if self._rules is None:
            from .pricing_rules_service import PricingRulesService
            self._rules = PricingRulesService(self.db)
        return self._rules

    # ------------------------------------------------------------------ guards

    @staticmethod
    def _whitelist() -> set[str]:
        raw = settings.IIKO_PRICE_PUSH_DEPARTMENTS or ""
        return {d.strip() for d in raw.split(",") if d.strip()}

    def _check_enabled(self, department_id: str) -> None:
        if not settings.IIKO_PRICE_PUSH_ENABLED:
            raise PriceOrderError(
                "push_disabled",
                "Выгрузка цен в iiko выключена (IIKO_PRICE_PUSH_ENABLED=False)",
                http_status=503,
            )
        allowed = self._whitelist()
        if allowed and str(department_id) not in allowed:
            raise PriceOrderError(
                "department_not_allowed",
                "Точка не входит в белый список IIKO_PRICE_PUSH_DEPARTMENTS",
                http_status=403,
            )

    @staticmethod
    def _check_effective_date(effective_date: date) -> None:
        today = date.today()
        if effective_date < today:
            raise PriceOrderError("date_in_past",
                                  "Дата вступления в силу не может быть в прошлом")
        max_date = today + timedelta(days=settings.IIKO_PRICE_ORDER_MAX_LEAD_DAYS)
        if effective_date > max_date:
            raise PriceOrderError(
                "date_too_far",
                f"Дата вступления в силу дальше {settings.IIKO_PRICE_ORDER_MAX_LEAD_DAYS} дней",
            )

    def _department(self, department_id: str) -> Any:
        row = self.db.execute(
            text("""
                SELECT id::text AS id, name, iiko_source_domain
                FROM departments WHERE id = CAST(:d AS uuid)
            """),
            {"d": department_id},
        ).fetchone()
        if not row:
            raise PriceOrderError("department_not_found",
                                  f"Подразделение {department_id} не найдено", http_status=404)
        if not row.iiko_source_domain:
            raise PriceOrderError(
                "department_no_domain",
                f"У точки «{row.name}» не задан iiko_source_domain — некуда отправлять приказ",
            )
        return row

    # ------------------------------------------------------------- сборка

    def _catalog_state(self, department_id: str, product_ids: list[int]) -> dict[int, dict]:
        """Действующая цена по каталогу + признаки, мешающие простому приказу.

        «Цена SKU» = базовая серия (price_type='BASE', size IS NULL) — тем же
        DISTINCT ON, что и в оптимизаторе; AVG по размерам брать нельзя.
        """
        if not product_ids:
            return {}
        rows = self.db.execute(
            text("""
                SELECT DISTINCT ON (product_id)
                    product_id, price, date_from, document_id::text AS document_id,
                    product_size_id::text AS product_size_id, price_type
                FROM sku_catalog_price
                WHERE department_id = CAST(:dept AS uuid)
                  AND product_id = ANY(:pids)
                  AND price > 0 AND NOT is_stale
                  AND date_from <= CURRENT_DATE AND date_to > CURRENT_DATE
                ORDER BY product_id, (price_type <> 'BASE'),
                         (product_size_id IS NOT NULL), product_size_id, id
            """),
            {"dept": department_id, "pids": product_ids},
        ).fetchall()
        state = {
            r.product_id: {
                "price": _f(r.price),
                "date_from": r.date_from,
                "document_id": r.document_id,
                "product_size_id": r.product_size_id,
                "price_type": r.price_type,
            }
            for r in rows
        }

        # Размеры и небазовые серии: в нашем контуре их нет, но если появятся —
        # честно исключаем позицию, а не отправляем приказ «как получится».
        variants = self.db.execute(
            text("""
                SELECT product_id,
                       COUNT(*) FILTER (WHERE product_size_id IS NOT NULL) AS sized,
                       COUNT(*) FILTER (WHERE price_type <> 'BASE') AS non_base
                FROM sku_catalog_price
                WHERE department_id = CAST(:dept AS uuid)
                  AND product_id = ANY(:pids)
                  AND NOT is_stale
                  AND date_from <= CURRENT_DATE AND date_to > CURRENT_DATE
                GROUP BY product_id
            """),
            {"dept": department_id, "pids": product_ids},
        ).fetchall()
        for v in variants:
            if v.product_id in state:
                state[v.product_id]["has_sizes"] = bool(v.sized)
                state[v.product_id]["has_non_base"] = bool(v.non_base)
        return state

    def _candidates(self, department_id: str, rec_ids: Optional[list[int]] = None,
                    lock: bool = False) -> list:
        conditions = [
            "pr.department_id = CAST(:dept AS uuid)",
            "pr.status = 'approved'",
            "pr.order_id IS NULL",
        ]
        params: dict = {"dept": department_id}
        if rec_ids:
            conditions.append("pr.id = ANY(:ids)")
            params["ids"] = rec_ids
        # FOR UPDATE только по price_recommendation: JOIN'ы блокировать незачем
        suffix = " FOR UPDATE OF pr" if lock else ""
        return self.db.execute(
            text(f"""
                SELECT pr.id, pr.product_id, pr.current_price, pr.recommended_price,
                       pr.delta_pct, pr.delta_gp, pr.cogs, pr.menu_role, pr.reviewed_at,
                       pr.rec_type,
                       p.name AS product_name, p.code AS product_code,
                       p.iiko_product_id::text AS iiko_product_id,
                       p.iiko_source_domain
                FROM price_recommendation pr
                JOIN product p ON p.id = pr.product_id
                WHERE {' AND '.join(conditions)}
                ORDER BY pr.delta_gp DESC NULLS LAST, pr.id{suffix}
            """),
            params,
        ).fetchall()

    def _reject_reason(self, rec, dept, catalog: Optional[dict]) -> Optional[str]:
        """Причина, по которой позиция не идёт в приказ, либо None."""
        new_price = _f(rec.recommended_price)
        old_price = _f(rec.current_price)

        if rec.iiko_source_domain != dept.iiko_source_domain:
            return (f"товар заведён в другой базе iiko ({rec.iiko_source_domain}), "
                    f"а точка — в {dept.iiko_source_domain}")
        if not rec.iiko_product_id:
            return "у товара нет iiko_product_id"
        if new_price is None or new_price <= 0:
            return "некорректная рекомендованная цена"
        if old_price is not None and abs(new_price - old_price) <= PRICE_MATCH_TOLERANCE:
            return "рекомендованная цена совпадает с текущей"
        if rec.reviewed_at and (date.today() - rec.reviewed_at.date()).days > APPROVED_TTL_DAYS:
            return f"утверждена более {APPROVED_TTL_DAYS} дней назад — базис устарел"

        if not catalog:
            return "в каталоге iiko нет действующей цены — базис не подтверждён"
        if catalog.get("has_sizes"):
            return "у позиции есть цены по размерам — приказ собирается вручную"
        if catalog.get("has_non_base"):
            return "у позиции есть цены по расписанию — приказ собирается вручную"
        if old_price is not None and abs(catalog["price"] - old_price) > PRICE_MATCH_TOLERANCE:
            return (f"цена в iiko ({catalog['price']:.0f}) отличается от базиса решения "
                    f"({old_price:.0f}) — перегенерируйте рекомендацию")

        rules = self.rules.get_effective_rules(rec.product_id, str(dept.id), None)
        # rec_type обязателен: для отката снимаются ROLLBACK_RELAXED_RULES.
        # Без него возврат к прежней цене отсекался правилом rounding — исходные
        # цены не кратны шагу 50 (1360, 1010, 810, 430 ₸), и приказ на откат
        # собрать было нельзя в принципе.
        ok, violations = self.rules.check_recommendation(
            current_price=old_price or catalog["price"],
            candidate_price=new_price,
            cogs=_f(rec.cogs),
            menu_role=rec.menu_role,
            last_change_date=catalog.get("date_from"),
            rules=rules,
            rec_type=rec.rec_type,
        )
        if not ok:
            return "нарушены правила: " + "; ".join(violations)
        return None

    def build_preview(self, department_id: str, effective_date: date,
                      rec_ids: Optional[list[int]] = None) -> dict:
        """Что уедет в iiko, если нажать «Отправить». Ничего не пишет."""
        self._check_enabled(department_id)
        self._check_effective_date(effective_date)
        dept = self._department(department_id)

        candidates = self._candidates(department_id, rec_ids)
        catalog = self._catalog_state(department_id, [c.product_id for c in candidates])

        items: list[dict] = []
        excluded: list[dict] = []
        for rec in candidates:
            reason = self._reject_reason(rec, dept, catalog.get(rec.product_id))
            entry = {
                "recommendation_id": rec.id,
                "product_id": rec.product_id,
                "product_code": rec.product_code,
                "product_name": rec.product_name,
                "menu_role": rec.menu_role,
                "rec_type": rec.rec_type,
                "old_price": _f(rec.current_price),
                "new_price": _f(rec.recommended_price),
                "delta_pct": _f(rec.delta_pct),
                "delta_gp": _f(rec.delta_gp),
            }
            if reason:
                excluded.append({**entry, "reason": reason})
            else:
                entry["iiko_product_id"] = rec.iiko_product_id
                entry["catalog_document_id"] = (catalog.get(rec.product_id) or {}).get("document_id")
                items.append(entry)

        over_limit = max(0, len(items) - settings.IIKO_PRICE_ORDER_MAX_ITEMS)
        if over_limit:
            # хвост по возрастанию ΔGP отсекаем явно, а не молча
            for entry in items[settings.IIKO_PRICE_ORDER_MAX_ITEMS:]:
                excluded.append({
                    **{k: v for k, v in entry.items()
                       if k not in ("iiko_product_id", "catalog_document_id")},
                    "reason": (f"превышен потолок {settings.IIKO_PRICE_ORDER_MAX_ITEMS} позиций "
                               f"в приказе — отправьте отдельным приказом"),
                })
            items = items[:settings.IIKO_PRICE_ORDER_MAX_ITEMS]

        return {
            "department_id": str(dept.id),
            "department_name": dept.name,
            "iiko_source_domain": dept.iiko_source_domain,
            "effective_date": effective_date.isoformat(),
            "iiko_order_status": settings.IIKO_PRICE_ORDER_STATUS,
            "items": items,
            "excluded": excluded,
            "n_items": len(items),
            "n_excluded": len(excluded),
            "total_delta_gp": round(sum(i["delta_gp"] or 0 for i in items), 2),
            "existing_order": self._open_order_for(department_id, effective_date),
        }

    def _open_order_for(self, department_id: str, effective_date: date) -> Optional[dict]:
        row = self.db.execute(
            text("""
                SELECT id, status, iiko_document_number
                FROM price_change_order
                WHERE department_id = CAST(:d AS uuid) AND effective_date = :eff
                  AND status IN ('draft', 'sending', 'sent')
            """),
            {"d": department_id, "eff": effective_date},
        ).fetchone()
        return {"id": row.id, "status": row.status,
                "iiko_document_number": row.iiko_document_number} if row else None

    # ------------------------------------------------------------- payload

    async def _carried_attributes(self, writer: IikoMenuChangeWriter,
                                  items: list[dict], department_id: str) -> dict[str, dict]:
        """Атрибуты позиций из действующих приказов: (iiko_product_id) → dict.

        Приказ задаёт позицию целиком: если не перенести dishOfDay / флаерную
        программу / ценовые категории, новый приказ их обнулит. Ошибку чтения
        глотаем — фолбэк на пустые значения (в нашем контуре они и так пусты),
        но пишем предупреждение в лог.
        """
        doc_ids = {i["catalog_document_id"] for i in items if i.get("catalog_document_id")}
        wanted = {i["iiko_product_id"] for i in items}
        carried: dict[str, dict] = {}
        for doc_id in doc_ids:
            try:
                doc = await writer.get_order(doc_id)
            except Exception as e:
                logger.warning("Не удалось прочитать приказ %s для переноса атрибутов: %s",
                               doc_id, e)
                continue
            if not doc:
                continue
            for src in doc.get("items") or []:
                pid = src.get("productId")
                if pid in wanted and str(src.get("departmentId")) == str(department_id):
                    carried[pid] = {
                        "dishOfDay": bool(src.get("dishOfDay")),
                        "flyerProgram": bool(src.get("flyerProgram")),
                        "pricesForCategories": src.get("pricesForCategories") or [],
                        "includeForCategories": src.get("includeForCategories") or [],
                    }
        return carried

    @staticmethod
    def _build_payload(department_id: str, effective_date: date, items: list[dict],
                       carried: dict[str, dict], comment: str,
                       iiko_status: str) -> dict:
        return {
            "dateIncoming": effective_date.isoformat(),
            "status": iiko_status,
            "comment": comment,
            # НЕ ПАРАМЕТР: true вычистил бы из меню всё, чего нет в документе
            "deletePreviousMenu": False,
            "dateTo": IIKO_DATE_TO_INFINITY,
            "items": [
                {
                    "departmentId": str(department_id),
                    "productId": i["iiko_product_id"],
                    "productSizeId": None,
                    "including": True,
                    "price": i["new_price"],
                    **(carried.get(i["iiko_product_id"]) or {
                        "dishOfDay": False,
                        "flyerProgram": False,
                        "pricesForCategories": [],
                        "includeForCategories": [],
                    }),
                }
                for i in items
            ],
        }

    # ------------------------------------------------------------- отправка

    async def send_order(self, department_id: str, effective_date: date,
                         rec_ids: Optional[list[int]] = None,
                         created_by: Optional[str] = None,
                         actor: Optional[str] = None,
                         dry_run: bool = False) -> dict:
        preview = self.build_preview(department_id, effective_date, rec_ids)
        if not preview["items"]:
            raise PriceOrderError(
                "no_items",
                "Нет позиций для приказа: " + (
                    f"все {preview['n_excluded']} утверждённых позиций отклонены проверками"
                    if preview["n_excluded"] else "нет утверждённых рекомендаций без приказа"
                ),
            )
        if preview["existing_order"] and not dry_run:
            ex = preview["existing_order"]
            raise PriceOrderError(
                "order_exists",
                f"На эту дату уже есть приказ #{ex['id']} (статус {ex['status']}) — "
                f"отмените его или выберите другую дату",
                http_status=409,
            )

        dept_domain = preview["iiko_source_domain"]
        domains = [d.strip() for d in settings.IIKO_DOMAINS.split(",") if d.strip()]
        writer = IikoMenuChangeWriter(base_url_for_host(dept_domain, domains))
        carried = await self._carried_attributes(writer, preview["items"], department_id)

        if dry_run:
            payload = self._build_payload(
                department_id, effective_date, preview["items"], carried,
                comment="SF#dry-run", iiko_status=settings.IIKO_PRICE_ORDER_STATUS,
            )
            return {**preview, "status": "dry_run", "payload": payload}

        order_id = self._insert_order(preview, department_id, effective_date, created_by)
        comment = (f"{marker_for(order_id)} Sales Forecast: {preview['n_items']} поз., "
                   f"ожидаемый эффект {preview['total_delta_gp']:.0f} тг/нед")
        payload = self._build_payload(
            department_id, effective_date, preview["items"], carried,
            comment=comment, iiko_status=settings.IIKO_PRICE_ORDER_STATUS,
        )
        self.db.execute(
            text("""UPDATE price_change_order
                    SET request_payload = CAST(:p AS jsonb), status = 'sending'
                    WHERE id = :id"""),
            {"p": _json(payload), "id": order_id},
        )
        self.db.commit()

        try:
            doc = await writer.create_order(payload)
        except IikoOrderError as e:
            self._fail_order(order_id, str(e), department_id, actor)
            raise PriceOrderError("iiko_rejected", str(e), http_status=502)
        except Exception as e:
            # Ответ не дошёл — документ мог создаться. Ищем сироту по маркеру;
            # POST не повторяем ни при каких условиях.
            logger.error("POST menuChange оборвался (приказ %s): %s", order_id, e, exc_info=True)
            doc = None
            try:
                doc = await writer.find_by_marker(
                    marker_for(order_id), effective_date.isoformat(), effective_date.isoformat())
            except Exception as probe_error:
                logger.error("Сверка после обрыва не удалась: %s", probe_error)
            if not doc:
                self._mark_unknown(order_id, str(e))
                raise PriceOrderError(
                    "send_unknown",
                    "Связь с iiko оборвалась, судьба приказа неизвестна. Приказ помечен "
                    "«отправляется»; ночная сверка (03:25) или кнопка «Сверить» определит "
                    "исход. Повторно не отправляйте — можно создать дубль.",
                    http_status=504,
                )
            logger.info("Приказ %s найден в iiko по маркеру после обрыва", order_id)

        return self._complete_order(order_id, doc, preview, department_id, actor)

    def _insert_order(self, preview: dict, department_id: str,
                      effective_date: date, created_by: Optional[str]) -> int:
        try:
            order_id = self.db.execute(
                text("""
                    INSERT INTO price_change_order
                        (department_id, iiko_source_domain, effective_date, status,
                         n_items, request_payload, created_by)
                    VALUES (CAST(:dept AS uuid), :domain, :eff, 'draft', :n,
                            CAST('{}' AS jsonb), CAST(:by AS uuid))
                    RETURNING id
                """),
                {
                    "dept": department_id,
                    "domain": preview["iiko_source_domain"],
                    "eff": effective_date,
                    "n": preview["n_items"],
                    "by": created_by,
                },
            ).scalar()
            for item in preview["items"]:
                self.db.execute(
                    text("""
                        INSERT INTO price_change_order_item
                            (order_id, recommendation_id, product_id, iiko_product_id,
                             old_price, new_price)
                        VALUES (:oid, :rid, :pid, CAST(:iiko_pid AS uuid), :old, :new)
                    """),
                    {
                        "oid": order_id, "rid": item["recommendation_id"],
                        "pid": item["product_id"], "iiko_pid": item["iiko_product_id"],
                        "old": item["old_price"], "new": item["new_price"],
                    },
                )
            self.db.commit()
            return order_id
        except IntegrityError as e:
            # гонка двух отправок: уникальные индексы 039 — последняя линия
            # обороны, и она должна читаться как конфликт, а не как 500
            self.db.rollback()
            constraint = str(getattr(e.orig, "diag", None) and e.orig.diag.constraint_name or "")
            if "uq_price_order_item_rec" in constraint:
                raise PriceOrderError(
                    "recommendation_already_sent",
                    "Часть позиций уже уехала другим приказом — обновите страницу",
                    http_status=409,
                )
            raise PriceOrderError(
                "order_exists",
                "На эту дату приказ уже создаётся параллельно — обновите страницу",
                http_status=409,
            )
        except Exception:
            self.db.rollback()
            raise

    def _complete_order(self, order_id: int, doc: dict, preview: dict,
                        department_id: str, actor: Optional[str]) -> dict:
        self.db.execute(
            text("""
                UPDATE price_change_order
                SET status = 'sent', sent_at = NOW(), error_message = NULL,
                    iiko_document_id = CAST(:doc_id AS uuid),
                    iiko_document_number = :number,
                    iiko_status = :iiko_status,
                    response_payload = CAST(:resp AS jsonb)
                WHERE id = :id
            """),
            {
                "id": order_id, "doc_id": doc.get("id"),
                "number": doc.get("documentNumber"), "iiko_status": doc.get("status"),
                "resp": _json(doc),
            },
        )
        rec_ids = [i["recommendation_id"] for i in preview["items"]]
        self.db.execute(
            text("""UPDATE price_recommendation
                    SET order_id = :oid, pushed_at = NOW()
                    WHERE id = ANY(:ids)"""),
            {"oid": order_id, "ids": rec_ids},
        )
        log_audit(
            self.db, "price_order", order_id, "sent", actor=actor,
            department_id=department_id,
            details={
                "iiko_document_id": doc.get("id"),
                "iiko_document_number": doc.get("documentNumber"),
                "iiko_status": doc.get("status"),
                "effective_date": preview["effective_date"],
                "n_items": preview["n_items"],
                "total_delta_gp": preview["total_delta_gp"],
                "recommendation_ids": rec_ids,
            },
        )
        self.db.commit()
        logger.info("Приказ %s отправлен: документ %s (%s), %d позиций",
                    order_id, doc.get("documentNumber"), doc.get("status"), len(rec_ids))
        return {
            "status": "ok",
            "order_id": order_id,
            "iiko_document_id": doc.get("id"),
            "iiko_document_number": doc.get("documentNumber"),
            "iiko_status": doc.get("status"),
            "n_items": preview["n_items"],
            "n_excluded": preview["n_excluded"],
            "excluded": preview["excluded"],
            "total_delta_gp": preview["total_delta_gp"],
            "effective_date": preview["effective_date"],
        }

    def _fail_order(self, order_id: int, message: str,
                    department_id: str, actor: Optional[str]) -> None:
        self.db.rollback()
        self.db.execute(
            text("""UPDATE price_change_order
                    SET status = 'failed', error_message = :msg WHERE id = :id"""),
            {"id": order_id, "msg": message[:2000]},
        )
        log_audit(self.db, "price_order", order_id, "failed", actor=actor,
                  department_id=department_id, details={"error": message[:500]})
        self.db.commit()

    def _mark_unknown(self, order_id: int, message: str) -> None:
        """Статус 'sending' сохраняем — судьбу определит сверка."""
        self.db.rollback()
        self.db.execute(
            text("""UPDATE price_change_order
                    SET error_message = :msg WHERE id = :id"""),
            {"id": order_id, "msg": f"обрыв связи: {message}"[:2000]},
        )
        self.db.commit()

    # --------------------------------------------------------------- отмена

    async def cancel_order(self, order_id: int, actor: Optional[str] = None,
                           reason: Optional[str] = None) -> dict:
        order = self._order_row(order_id)
        if order.status not in ("sent", "sending"):
            raise PriceOrderError("not_cancellable",
                                  f"Приказ в статусе '{order.status}' — отменять нечего",
                                  http_status=409)
        if not order.iiko_document_id:
            raise PriceOrderError("no_document",
                                  "У приказа нет документа iiko — сначала выполните сверку",
                                  http_status=409)

        domains = [d.strip() for d in settings.IIKO_DOMAINS.split(",") if d.strip()]
        writer = IikoMenuChangeWriter(base_url_for_host(order.iiko_source_domain, domains))

        if order.effective_date >= date.today():
            # приказ ещё не вступил в силу (или вступает сегодня) — iiko
            # разрешает редактировать документ целиком, помечаем DELETED
            payload = dict(order.request_payload or {})
            payload["id"] = str(order.iiko_document_id)
            payload["status"] = "DELETED"
            if order.iiko_document_number:
                payload["documentNumber"] = order.iiko_document_number
            try:
                doc = await writer.update_order(payload)
            except IikoOrderError as e:
                raise PriceOrderError("iiko_rejected",
                                      f"iiko не принял отмену: {e}", http_status=502)
            self._mark_cancelled(order, actor, method="deleted", reason=reason,
                                 iiko_status=(doc or {}).get("status", "DELETED"))
            return {"status": "ok", "order_id": order_id, "method": "deleted",
                    "iiko_status": (doc or {}).get("status", "DELETED")}

        # приказ уже действует: iiko разрешает менять только dateTo, поэтому
        # откат — обратный приказ, возвращающий базисные цены
        return await self._reverse_order(order, writer, actor, reason)

    async def _reverse_order(self, order, writer: IikoMenuChangeWriter,
                             actor: Optional[str], reason: Optional[str]) -> dict:
        items = self.db.execute(
            text("""SELECT product_id, iiko_product_id::text AS iiko_product_id,
                           old_price, new_price
                    FROM price_change_order_item WHERE order_id = :id"""),
            {"id": order.id},
        ).fetchall()
        if not items:
            raise PriceOrderError("empty_order", "В приказе нет позиций для отката")

        effective = date.today() + timedelta(days=1)
        if self._open_order_for(str(order.department_id), effective):
            raise PriceOrderError(
                "order_exists",
                f"На {effective.isoformat()} уже есть приказ — отмените его или "
                f"откатите цены вручную",
                http_status=409,
            )

        reverse_id = self.db.execute(
            text("""
                INSERT INTO price_change_order
                    (department_id, iiko_source_domain, effective_date, status,
                     n_items, request_payload, reverses_order_id)
                VALUES (:dept, :domain, :eff, 'draft', :n, CAST('{}' AS jsonb), :rev)
                RETURNING id
            """),
            {"dept": order.department_id, "domain": order.iiko_source_domain,
             "eff": effective, "n": len(items), "rev": order.id},
        ).scalar()
        for it in items:
            self.db.execute(
                text("""
                    INSERT INTO price_change_order_item
                        (order_id, recommendation_id, product_id, iiko_product_id,
                         old_price, new_price)
                    VALUES (:oid, NULL, :pid, CAST(:iiko_pid AS uuid), :old, :new)
                """),
                # в обратном приказе «новая» цена — это прежний базис
                {"oid": reverse_id, "pid": it.product_id,
                 "iiko_pid": it.iiko_product_id,
                 "old": _f(it.new_price), "new": _f(it.old_price)},
            )
        self.db.commit()

        # атрибуты берём из действующих приказов тех же позиций — откат обязан
        # вернуть не только цену, но и «хит дня»/флаерную программу
        catalog = self._catalog_state(str(order.department_id),
                                      [it.product_id for it in items])
        payload_items = [{
            "recommendation_id": None,
            "iiko_product_id": it.iiko_product_id,
            "new_price": _f(it.old_price),
            "catalog_document_id": (catalog.get(it.product_id) or {}).get("document_id"),
        } for it in items]
        carried = await self._carried_attributes(writer, payload_items,
                                                 str(order.department_id))
        payload = self._build_payload(
            str(order.department_id), effective, payload_items, carried,
            comment=f"{marker_for(reverse_id)} Sales Forecast: откат приказа "
                    f"{order.iiko_document_number or order.id}",
            iiko_status=settings.IIKO_PRICE_ORDER_STATUS,
        )
        self.db.execute(
            text("""UPDATE price_change_order
                    SET request_payload = CAST(:p AS jsonb), status = 'sending'
                    WHERE id = :id"""),
            {"p": _json(payload), "id": reverse_id},
        )
        self.db.commit()

        try:
            doc = await writer.create_order(payload)
        except IikoOrderError as e:
            self._fail_order(reverse_id, str(e), str(order.department_id), actor)
            raise PriceOrderError("iiko_rejected",
                                  f"iiko не принял обратный приказ: {e}", http_status=502)

        self.db.execute(
            text("""
                UPDATE price_change_order
                SET status = 'sent', sent_at = NOW(),
                    iiko_document_id = CAST(:doc_id AS uuid),
                    iiko_document_number = :number, iiko_status = :st,
                    response_payload = CAST(:resp AS jsonb)
                WHERE id = :id
            """),
            {"id": reverse_id, "doc_id": doc.get("id"),
             "number": doc.get("documentNumber"), "st": doc.get("status"),
             "resp": _json(doc)},
        )
        self._mark_cancelled(order, actor, method="reversed", reason=reason,
                             iiko_status=None, reverse_order_id=reverse_id)
        return {"status": "ok", "order_id": order.id, "method": "reversed",
                "reverse_order_id": reverse_id,
                "iiko_document_number": doc.get("documentNumber"),
                "effective_date": effective.isoformat()}

    def _mark_cancelled(self, order, actor: Optional[str], method: str,
                        reason: Optional[str], iiko_status: Optional[str],
                        reverse_order_id: Optional[int] = None) -> None:
        self.db.execute(
            text("""
                UPDATE price_change_order
                SET status = 'cancelled', cancelled_at = NOW(),
                    iiko_status = COALESCE(:st, iiko_status)
                WHERE id = :id
            """),
            {"id": order.id, "st": iiko_status},
        )
        # рекомендации, не успевшие стать applied, возвращаются в пул
        # утверждённых — иначе висели бы «отправленными» навсегда
        released = self.db.execute(
            text("""
                UPDATE price_recommendation
                SET order_id = NULL, pushed_at = NULL
                WHERE order_id = :id AND status = 'approved'
                RETURNING id
            """),
            {"id": order.id},
        ).fetchall()
        log_audit(
            self.db, "price_order", order.id, "cancelled", actor=actor,
            department_id=str(order.department_id),
            details={"method": method, "reason": reason,
                     "reverse_order_id": reverse_order_id,
                     "released_recommendations": [r[0] for r in released]},
        )
        self.db.commit()

    # --------------------------------------------------------------- сверка

    async def sync_order_status(self, order_id: int) -> dict:
        """Сверить наше состояние с iiko: приказ могли провести или удалить
        руками в бэк-офисе, а 'sending' — вообще не иметь документа."""
        order = self._order_row(order_id)
        domains = [d.strip() for d in settings.IIKO_DOMAINS.split(",") if d.strip()]
        writer = IikoMenuChangeWriter(base_url_for_host(order.iiko_source_domain, domains))

        doc = None
        if order.iiko_document_id:
            doc = await writer.get_order(str(order.iiko_document_id))
        elif order.status == "sending":
            eff = order.effective_date.isoformat()
            doc = await writer.find_by_marker(marker_for(order.id), eff, eff)

        if not doc:
            if order.status == "sending":
                self.db.execute(
                    text("""UPDATE price_change_order
                            SET status = 'failed',
                                error_message = COALESCE(error_message, '') ||
                                    ' | сверка: документ в iiko не найден'
                            WHERE id = :id"""),
                    {"id": order.id},
                )
                self.db.commit()
                return {"status": "ok", "order_id": order.id, "result": "not_found",
                        "order_status": "failed"}
            return {"status": "ok", "order_id": order.id, "result": "not_found",
                    "order_status": order.status}

        iiko_status = doc.get("status")
        new_status = order.status
        if order.status == "sending":
            new_status = "sent"
        if iiko_status == "DELETED" and order.status != "cancelled":
            # удалили в бэк-офисе — наше состояние обязано это отразить
            new_status = "cancelled"

        self.db.execute(
            text("""
                UPDATE price_change_order
                SET iiko_status = :st,
                    status = :status,
                    iiko_document_id = COALESCE(iiko_document_id, CAST(:doc_id AS uuid)),
                    iiko_document_number = COALESCE(iiko_document_number, :number),
                    sent_at = COALESCE(sent_at, NOW()),
                    cancelled_at = CASE WHEN :status = 'cancelled'
                                        THEN COALESCE(cancelled_at, NOW()) ELSE cancelled_at END,
                    response_payload = CAST(:resp AS jsonb)
                WHERE id = :id
            """),
            {"id": order.id, "st": iiko_status, "status": new_status,
             "doc_id": doc.get("id"), "number": doc.get("documentNumber"),
             "resp": _json(doc)},
        )
        if new_status == "cancelled":
            self.db.execute(
                text("""UPDATE price_recommendation
                        SET order_id = NULL, pushed_at = NULL
                        WHERE order_id = :id AND status = 'approved'"""),
                {"id": order.id},
            )
        if new_status != order.status:
            log_audit(self.db, "price_order", order.id, f"sync:{new_status}",
                      actor="scheduler", department_id=str(order.department_id),
                      details={"iiko_status": iiko_status, "was": order.status})
        self.db.commit()
        return {"status": "ok", "order_id": order.id, "result": "synced",
                "order_status": new_status, "iiko_status": iiko_status}

    async def sync_pending(self, days: int = 30) -> dict:
        """Ночная сверка всех живых приказов (джоб 03:25)."""
        rows = self.db.execute(
            text("""
                SELECT id FROM price_change_order
                WHERE status IN ('sent', 'sending')
                  AND created_at >= NOW() - make_interval(days => :days)
                ORDER BY id
            """),
            {"days": days},
        ).fetchall()
        synced, errors = 0, []
        for row in rows:
            try:
                await self.sync_order_status(row[0])
                synced += 1
            except Exception as e:
                self.db.rollback()
                logger.error("Сверка приказа %s не удалась: %s", row[0], e)
                errors.append(f"order {row[0]}: {e}")
        return {"status": "ok" if not errors else "partial",
                "checked": len(rows), "synced": synced, "errors": errors}

    # ------------------------------------------------------------- чтение

    def _order_row(self, order_id: int):
        row = self.db.execute(
            text("""
                SELECT id, department_id::text AS department_id, iiko_source_domain,
                       effective_date, status, iiko_status, iiko_document_id::text
                       AS iiko_document_id, iiko_document_number, request_payload
                FROM price_change_order WHERE id = :id
            """),
            {"id": order_id},
        ).fetchone()
        if not row:
            raise PriceOrderError("order_not_found", f"Приказ {order_id} не найден",
                                  http_status=404)
        return row

    def list_orders(self, department_id: Optional[str] = None,
                    status: Optional[str] = None, limit: int = 50) -> list[dict]:
        conditions = ["1=1"]
        params: dict = {"limit": limit}
        if department_id:
            conditions.append("o.department_id = CAST(:dept AS uuid)")
            params["dept"] = department_id
        if status:
            conditions.append("o.status = :status")
            params["status"] = status
        rows = self.db.execute(
            text(f"""
                SELECT o.id, o.department_id::text AS department_id, d.name AS department_name,
                       o.effective_date, o.status, o.iiko_status, o.iiko_document_number,
                       o.iiko_document_id::text AS iiko_document_id, o.n_items,
                       o.error_message, o.created_at, o.sent_at, o.cancelled_at,
                       o.reverses_order_id,
                       (SELECT COALESCE(SUM(pr.delta_gp), 0) FROM price_recommendation pr
                        WHERE pr.order_id = o.id) AS total_delta_gp,
                       (SELECT COUNT(*) FROM price_recommendation pr
                        WHERE pr.order_id = o.id AND pr.status = 'applied') AS n_applied
                FROM price_change_order o
                JOIN departments d ON d.id = o.department_id
                WHERE {' AND '.join(conditions)}
                ORDER BY o.created_at DESC
                LIMIT :limit
            """),
            params,
        ).fetchall()
        return [dict(r._mapping) for r in rows]

    def get_order(self, order_id: int) -> dict:
        row = self.db.execute(
            text("""
                SELECT o.*, d.name AS department_name
                FROM price_change_order o
                JOIN departments d ON d.id = o.department_id
                WHERE o.id = :id
            """),
            {"id": order_id},
        ).fetchone()
        if not row:
            raise PriceOrderError("order_not_found", f"Приказ {order_id} не найден",
                                  http_status=404)
        items = self.db.execute(
            text("""
                SELECT i.id, i.recommendation_id, i.product_id, p.name AS product_name,
                       p.code AS product_code, i.old_price, i.new_price,
                       pr.status AS recommendation_status, pr.delta_gp, pr.applied_at
                FROM price_change_order_item i
                JOIN product p ON p.id = i.product_id
                LEFT JOIN price_recommendation pr ON pr.id = i.recommendation_id
                WHERE i.order_id = :id
                ORDER BY pr.delta_gp DESC NULLS LAST, i.id
            """),
            {"id": order_id},
        ).fetchall()
        out = dict(row._mapping)
        out["department_id"] = str(out["department_id"])
        out["iiko_document_id"] = str(out["iiko_document_id"]) if out["iiko_document_id"] else None
        out["items"] = [dict(i._mapping) for i in items]
        return out


def _json(value: Any) -> str:
    import json
    return json.dumps(value, ensure_ascii=False, default=str)
