"""Рекомендация заявки на цех по скоропортящимся позициям.

Задача: управляющий каждый день заказывает на точку торты, пирожные и прочую
готовую продукцию. Заказал мало — упустил выручку, заказал много — списал по
сроку годности. Обе ошибки стоят разных денег, поэтому «заказать средний
спрос» — заведомо неоптимально.

Модель — классический newsvendor. Оптимальный объём заказа равен квантилю
распределения спроса на уровне

    q* = Cu / (Cu + Co)

где ``Cu`` — цена нехватки (упущенная маржа = цена − себестоимость), а ``Co`` —
цена излишка (для скоропорта товар списывается целиком, то есть себестоимость).
Подставив, получаем ``q* = (цена − себестоимость) / цена``, то есть **процент
наценки и есть целевой уровень сервиса**. Для торта с маржой 70% выгодно
покрывать спрос в 70% дней и мириться со списаниями в остальные — упущенная
продажа дороже потерянной себестоимости.

Спрос оценивается по фактическим продажам того же дня недели: у выпечки
недельная сезонность сильнее любого тренда.

Продажи — цензурированная оценка спроса: в день, когда позиция кончилась к
обеду, настоящий спрос был выше зафиксированного. Дефицит определяется по
времени чеков: если последняя продажа позиции прошла сильно раньше последнего
чека точки и списаний в этот день не было, товар закончился. Остаток на складе
для такого детектора не годится — у скоропорта он обнуляется каждый день и
даёт ложный сигнал почти на каждой позиции.

Экономический эффект намеренно разделён на два разных по достоверности числа:
  * ``saving_from_reduction`` — снижение заказа там, где списания уже
    происходят. Это наблюдаемые деньги.
  * ``upside_from_increase`` — рост заказа там, где видим дефицит. Это оценка
    сверху: настоящий спрос неизвестен, мы знаем лишь, что он был выше
    проданного.
Складывать их в одну цифру нельзя, и сервис этого не делает.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings

logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_DAYS = 56          # 8 недель — 8 наблюдений на каждый день недели
MIN_OBSERVATIONS = 3                # меньше — рекомендация помечается как ненадёжная
MIN_SERVICE_LEVEL = 0.50            # не опускаемся ниже медианы спроса
MAX_SERVICE_LEVEL = 0.95            # и не гонимся за 100% покрытием
# Насколько раньше закрытия точки должна оборваться продажа позиции, чтобы
# считать это дефицитом, а не естественным затуханием спроса к вечеру.
STOCKOUT_GAP_HOURS = 3.0
# Доля дней недели с поставкой, ниже которой дневной объём заказа перестаёт
# быть корректной величиной: заказ должен покрывать спрос до следующего завоза.
MIN_DELIVERY_SHARE = 0.4


def _quantile(values: Sequence[float], q: float) -> float:
    """Квантиль по линейной интерполяции (как numpy.percentile), без numpy."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * max(0.0, min(1.0, q))
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    frac = pos - low
    return ordered[low] * (1 - frac) + ordered[high] * frac


def _revenue_column() -> str:
    return "ri.paid_sum" if settings.REVENUE_BASIS == "paid" else "ri.dish_sum"


class ProcurementRecommendationService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Публичный вход
    # ------------------------------------------------------------------

    def recommend_order(
        self,
        department_id: str,
        target_date: date,
        supplier_id: Optional[str] = None,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        min_supplied_sum: float = 0.0,
    ) -> Dict[str, Any]:
        """Рекомендуемая заявка на дату ``target_date``.

        ``supplier_id`` ограничивает позиции одним поставщиком (цехом);
        без него берутся все позиции, которые точка и закупает, и продаёт.
        """
        window_to = target_date - timedelta(days=1)
        window_from = window_to - timedelta(days=lookback_days - 1)
        weekday = target_date.weekday()

        products = self._candidate_products(
            department_id, window_from, window_to, supplier_id, min_supplied_sum
        )
        if not products:
            return {
                "department_id": department_id,
                "target_date": target_date.isoformat(),
                "weekday": weekday,
                "lookback_from": window_from.isoformat(),
                "lookback_to": window_to.isoformat(),
                "items": [],
                "totals": self._empty_totals(),
                "warnings": ["За выбранный период нет позиций, которые точка и закупает, и продаёт"],
            }

        product_ids = [p["product_id"] for p in products]
        sales = self._daily_series(
            department_id, window_from, window_to, product_ids, "sales")
        supply = self._daily_series(
            department_id, window_from, window_to, product_ids, "supply")
        writeoff = self._daily_series(
            department_id, window_from, window_to, product_ids, "writeoff")
        open_days, day_close = self._open_days(department_id, window_from, window_to)
        last_sale = self._last_sale_times(department_id, window_from, window_to, product_ids)

        items: List[Dict[str, Any]] = []
        for p in products:
            item = self._recommend_one(
                p, weekday, open_days, day_close,
                sales.get(p["product_id"], {}),
                supply.get(p["product_id"], {}),
                writeoff.get(p["product_id"], {}),
                last_sale.get(p["product_id"], {}),
            )
            if item:
                items.append(item)

        items.sort(key=lambda x: -max(x["saving_from_reduction"] or 0, x["upside_from_increase"] or 0))
        return {
            "department_id": department_id,
            "target_date": target_date.isoformat(),
            "weekday": weekday,
            "lookback_from": window_from.isoformat(),
            "lookback_to": window_to.isoformat(),
            "supplier_id": supplier_id,
            "items": items,
            "totals": self._totals(items),
            "warnings": self._warnings(items),
        }

    # ------------------------------------------------------------------
    # Кандидаты
    # ------------------------------------------------------------------

    def _candidate_products(
        self, department_id: str, window_from: date, window_to: date,
        supplier_id: Optional[str], min_supplied_sum: float,
    ) -> List[Dict[str, Any]]:
        """Позиции, которые точка и закупает, и продаёт как есть.

        Заготовки и полуфабрикаты (закупаются, но расходуются по техкартам)
        отсекаются требованием ненулевых прямых продаж: заказывать их надо от
        плана производства, а не от продаж SKU.
        """
        rows = self.db.execute(
            text(f"""
                WITH sup AS (
                    SELECT ii.product_id,
                           SUM(ii.amount)   AS amount,
                           SUM(ii.line_sum) AS line_sum,
                           AVG(NULLIF(ii.price, 0)) AS avg_price,
                           COUNT(DISTINCT ii.doc_date) AS days
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
                           SUM(ri.qty) AS qty,
                           SUM({_revenue_column()}) AS revenue,
                           SUM(ri.cost_price) AS cost
                    FROM receipt_item ri
                    JOIN receipt r ON r.id = ri.receipt_id AND r.open_date = ri.open_date
                    WHERE r.department_id = :dept ::uuid
                      AND r.open_date BETWEEN :from_date AND :to_date
                    GROUP BY ri.product_id
                )
                SELECT p.id AS product_id, p.name AS product_name, p.type AS product_type,
                       mu.name AS unit,
                       sup.amount AS supplied_amount, sup.line_sum AS supplied_sum,
                       sup.avg_price AS purchase_price, sup.days AS supply_days,
                       sold.qty AS sold_qty, sold.revenue AS revenue, sold.cost AS sold_cost
                FROM sup
                JOIN sold ON sold.product_id = sup.product_id
                JOIN product p ON p.id = sup.product_id
                LEFT JOIN measure_unit mu ON mu.id = p.measure_unit_id
                WHERE sold.qty > 0
                  AND sup.line_sum >= :min_sum
            """),
            {
                "dept": department_id, "from_date": window_from, "to_date": window_to,
                "supplier_id": supplier_id, "min_sum": min_supplied_sum,
            },
        ).fetchall()

        return [{
            "product_id": r.product_id,
            "product_name": r.product_name,
            "product_type": r.product_type,
            "unit": r.unit,
            "supplied_amount": float(r.supplied_amount or 0),
            "supplied_sum": float(r.supplied_sum or 0),
            "supply_days": r.supply_days or 0,
            "purchase_price": float(r.purchase_price) if r.purchase_price else None,
            "sold_qty": float(r.sold_qty or 0),
            "revenue": float(r.revenue or 0),
            "sold_cost": float(r.sold_cost or 0),
        } for r in rows]

    # ------------------------------------------------------------------
    # Дневные ряды
    # ------------------------------------------------------------------

    def _daily_series(
        self, department_id: str, window_from: date, window_to: date,
        product_ids: Sequence[int], kind: str,
    ) -> Dict[int, Dict[date, float]]:
        queries = {
            "sales": """
                SELECT ri.product_id, r.open_date AS d, SUM(ri.qty) AS v
                FROM receipt_item ri
                JOIN receipt r ON r.id = ri.receipt_id AND r.open_date = ri.open_date
                WHERE r.department_id = :dept ::uuid
                  AND r.open_date BETWEEN :from_date AND :to_date
                  AND ri.product_id = ANY(:ids)
                GROUP BY 1, 2
            """,
            "supply": """
                SELECT ii.product_id, ii.doc_date AS d, SUM(ii.amount) AS v
                FROM incoming_invoice_item ii
                JOIN incoming_invoice v2 ON v2.id = ii.invoice_id
                WHERE ii.department_id = :dept ::uuid
                  AND v2.status = 'PROCESSED'
                  AND ii.is_additional_expense = FALSE
                  AND ii.doc_date BETWEEN :from_date AND :to_date
                  AND ii.product_id = ANY(:ids)
                GROUP BY 1, 2
            """,
            "writeoff": """
                SELECT i.product_id, d2.doc_date AS d, SUM(i.amount) AS v
                FROM writeoff_document d2
                JOIN writeoff_item i ON i.document_id = d2.id
                WHERE d2.department_id = :dept ::uuid
                  AND d2.status = 'PROCESSED'
                  AND d2.doc_date BETWEEN :from_date AND :to_date
                  AND i.product_id = ANY(:ids)
                GROUP BY 1, 2
            """,
        }
        rows = self.db.execute(
            text(queries[kind]),
            {
                "dept": department_id, "from_date": window_from,
                "to_date": window_to, "ids": list(product_ids),
            },
        ).fetchall()

        series: Dict[int, Dict[date, float]] = defaultdict(dict)
        for r in rows:
            series[r.product_id][r.d] = float(r.v or 0)
        return series

    def _open_days(self, department_id: str, window_from: date, window_to: date):
        """Рабочие дни точки и время последнего чека в каждом из них.

        Нерабочие дни нельзя считать днями нулевого спроса, а время последнего
        чека задаёт точку отсчёта для детектора дефицита.
        """
        rows = self.db.execute(
            text("""
                SELECT open_date, MAX(COALESCE(open_time, close_time)) AS last_receipt
                FROM receipt
                WHERE department_id = :dept ::uuid
                  AND open_date BETWEEN :from_date AND :to_date
                GROUP BY open_date
                ORDER BY open_date
            """),
            {"dept": department_id, "from_date": window_from, "to_date": window_to},
        ).fetchall()
        days = [r.open_date for r in rows]
        close = {r.open_date: r.last_receipt for r in rows if r.last_receipt}
        return days, close

    def _last_sale_times(
        self, department_id: str, window_from: date, window_to: date,
        product_ids: Sequence[int],
    ) -> Dict[int, Dict[date, Any]]:
        """Время последней продажи каждой позиции в каждом дне."""
        rows = self.db.execute(
            text("""
                SELECT ri.product_id, r.open_date AS d,
                       MAX(COALESCE(r.open_time, r.close_time)) AS last_sale
                FROM receipt_item ri
                JOIN receipt r ON r.id = ri.receipt_id AND r.open_date = ri.open_date
                WHERE r.department_id = :dept ::uuid
                  AND r.open_date BETWEEN :from_date AND :to_date
                  AND ri.product_id = ANY(:ids)
                GROUP BY 1, 2
            """),
            {
                "dept": department_id, "from_date": window_from,
                "to_date": window_to, "ids": list(product_ids),
            },
        ).fetchall()
        out: Dict[int, Dict[date, Any]] = defaultdict(dict)
        for r in rows:
            if r.last_sale:
                out[r.product_id][r.d] = r.last_sale
        return out

    # ------------------------------------------------------------------
    # Расчёт по одной позиции
    # ------------------------------------------------------------------

    def _recommend_one(
        self, product: Dict[str, Any], weekday: int, open_days: List[date],
        day_close: Dict[date, Any], sales: Dict[date, float], supply: Dict[date, float],
        writeoff: Dict[date, float], last_sale: Dict[date, Any],
    ) -> Optional[Dict[str, Any]]:
        same_weekday = [d for d in open_days if d.weekday() == weekday]
        if not same_weekday:
            return None

        demand_series = [sales.get(d, 0.0) for d in same_weekday]
        observations = len(demand_series)

        sold_qty = product["sold_qty"]
        revenue = product["revenue"]
        sale_price = revenue / sold_qty if sold_qty else None
        # Себестоимость: цена закупки надёжнее, чем cost_price из чека
        # (последняя у комплексных блюд включает ингредиенты по техкарте).
        unit_cost = product["purchase_price"]
        if unit_cost is None and sold_qty:
            unit_cost = product["sold_cost"] / sold_qty if product["sold_cost"] else None

        base_level, margin = self._service_level(sale_price, unit_cost)

        stockout_days = sum(
            1 for d in same_weekday
            if self._is_stockout(d, day_close, last_sale, sales, writeoff)
        )
        censoring = stockout_days / observations if observations else 0.0
        # Спрос в дни дефицита был выше проданного, поэтому квантиль по продажам
        # занижен. Поднимаем уровень сервиса пропорционально доле таких дней —
        # мягко, а не прыжком к максимуму наблюдений.
        service_level = min(MAX_SERVICE_LEVEL, base_level + censoring * (1 - base_level))
        recommended = self._round_qty(_quantile(demand_series, service_level), product["unit"])

        current_practice = self._current_practice(same_weekday, supply)
        delta = recommended - current_practice if current_practice is not None else None

        # «Возим сейчас» усреднено по дням с поставкой, а рекомендация покрывает
        # один день. Если в этот день недели возят редко, сравнение неравноценно:
        # заказ должен покрывать спрос до следующего завоза, а не до вечера.
        supply_days_same_weekday = sum(1 for d in same_weekday if supply.get(d, 0.0) > 0)
        delivery_share = supply_days_same_weekday / observations if observations else 0.0

        written_qty = sum(writeoff.values())
        weekday_share = observations / len(open_days) if open_days else 0.0
        saving = upside = None
        if delta is not None and unit_cost:
            if delta < 0:
                # Реальные деньги: экономим не больше, чем фактически списали
                # в этот день недели за окно.
                avoidable = min(-delta * observations, written_qty * weekday_share)
                saving = round(max(0.0, avoidable) * unit_cost, 2)
            elif delta > 0 and sale_price:
                # Оценка сверху: предполагает, что весь добавленный объём
                # продастся. Настоящий спрос в дни дефицита неизвестен.
                upside = round(delta * observations * (sale_price - unit_cost), 2)

        return {
            "product_id": product["product_id"],
            "product_name": product["product_name"],
            "product_type": product["product_type"],
            "unit": product["unit"],
            "recommended_qty": recommended,
            "current_practice_qty": current_practice,
            "delta_qty": round(delta, 3) if delta is not None else None,
            "service_level": round(service_level, 3),
            "margin": round(margin, 3) if margin is not None else None,
            "sale_price": round(sale_price, 2) if sale_price else None,
            "unit_cost": round(unit_cost, 2) if unit_cost else None,
            "demand_observations": observations,
            "demand_median": round(_quantile(demand_series, 0.5), 3),
            "demand_max": round(max(demand_series), 3) if demand_series else 0.0,
            "stockout_days": stockout_days,
            "delivery_share": round(delivery_share, 2),
            "written_qty_period": round(written_qty, 3),
            "loss_rate": (
                round(written_qty / product["supplied_amount"], 4)
                if product["supplied_amount"] else None
            ),
            "saving_from_reduction": saving,
            "upside_from_increase": upside,
            "confidence": self._confidence(observations, censoring, delivery_share),
            "reason": self._reason(
                recommended, current_practice, written_qty, stockout_days, delivery_share,
            ),
        }

    @staticmethod
    def _is_stockout(
        day: date, day_close: Dict[date, Any], last_sale: Dict[date, Any],
        sales: Dict[date, float], writeoff: Dict[date, float],
    ) -> bool:
        """Позиция кончилась: продажи оборвались задолго до закрытия точки.

        Списание в тот же день снимает подозрение — товар был в наличии.
        """
        if sales.get(day, 0.0) <= 0 or writeoff.get(day, 0.0) > 0:
            return False
        closed_at = day_close.get(day)
        sold_at = last_sale.get(day)
        if closed_at is None or sold_at is None:
            return False
        return (closed_at - sold_at).total_seconds() >= STOCKOUT_GAP_HOURS * 3600

    @staticmethod
    def _service_level(sale_price: Optional[float], unit_cost: Optional[float]):
        """q* = (цена − себестоимость)/цена, зажатый в разумный коридор."""
        if not sale_price or not unit_cost or sale_price <= 0:
            return 0.7, None
        margin = (sale_price - unit_cost) / sale_price
        return max(MIN_SERVICE_LEVEL, min(MAX_SERVICE_LEVEL, margin)), margin

    @staticmethod
    def _current_practice(same_weekday: List[date], supply: Dict[date, float]) -> Optional[float]:
        """Сколько в среднем возят в этот день недели сейчас."""
        delivered = [supply.get(d, 0.0) for d in same_weekday]
        active = [v for v in delivered if v > 0]
        if not active:
            return 0.0
        return round(sum(active) / len(active), 3)

    @staticmethod
    def _round_qty(qty: float, unit: Optional[str]) -> float:
        """Штучное округляем до целого, весовое — до сотых."""
        if unit and unit.strip().lower() in {"шт", "порц", "уп"}:
            return float(round(qty))
        return round(qty, 2)

    @staticmethod
    def _confidence(observations: int, censoring: float, delivery_share: float) -> str:
        if observations < MIN_OBSERVATIONS:
            return "low"
        if censoring > 0.5:
            return "low"          # спрос сильно цензурирован, оценка снизу
        if delivery_share < MIN_DELIVERY_SHARE:
            return "low"          # возят редко: заказ должен покрывать не один день
        if observations < 6 or censoring > 0.25:
            return "medium"
        return "high"

    @staticmethod
    def _reason(
        recommended: float, current: Optional[float],
        written_qty: float, stockout_days: int, delivery_share: float,
    ) -> str:
        if delivery_share < MIN_DELIVERY_SHARE:
            return "Возят в этот день недели редко — объём на один день здесь занижен"
        if stockout_days:
            return f"Дефицит в {stockout_days} дн. — спрос выше поставки, стоит увеличить"
        if current is None:
            return "Нет истории поставок в этот день недели"
        if written_qty > 0 and recommended < current:
            return "Регулярные списания — везём больше, чем продаём"
        if recommended > current:
            return "Продажи стабильно выше поставки"
        return "Текущий объём близок к оптимальному"

    # ------------------------------------------------------------------
    # Итоги
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_totals() -> Dict[str, Any]:
        return {
            "positions": 0, "positions_to_decrease": 0, "positions_to_increase": 0,
            "saving_from_reduction": 0.0, "upside_from_increase": 0.0,
            "positions_with_stockout": 0,
        }

    @staticmethod
    def _totals(items: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "positions": len(items),
            "positions_to_decrease": sum(1 for i in items if (i["delta_qty"] or 0) < 0),
            "positions_to_increase": sum(1 for i in items if (i["delta_qty"] or 0) > 0),
            "positions_with_stockout": sum(1 for i in items if i["stockout_days"] > 0),
            # Две разные по достоверности величины — намеренно не складываются
            "saving_from_reduction": round(sum(i["saving_from_reduction"] or 0 for i in items), 2),
            "upside_from_increase": round(sum(i["upside_from_increase"] or 0 for i in items), 2),
        }

    @staticmethod
    def _warnings(items: List[Dict[str, Any]]) -> List[str]:
        warnings: List[str] = []
        low = sum(1 for i in items if i["confidence"] == "low")
        if low:
            warnings.append(
                f"{low} поз. с низкой надёжностью оценки: мало наблюдений или спрос упирался в поставку"
            )
        no_price = sum(1 for i in items if i["unit_cost"] is None or i["sale_price"] is None)
        if no_price:
            warnings.append(
                f"{no_price} поз. без цены или себестоимости — использован уровень сервиса по умолчанию 70%"
            )
        if any(i["upside_from_increase"] for i in items):
            warnings.append(
                "Выгода от увеличения заказа — оценка сверху: настоящий спрос в дни дефицита неизвестен"
            )
        return warnings
