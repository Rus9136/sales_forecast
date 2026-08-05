"""Оценка эффекта применённой цены: контрфакт по другим точкам + интервал.

Зачем отдельный модуль. Первый пилот (18 позиций, «Мадлен 18 мкр», 21.07.2026)
показал, что вся точность оценки держится на одном — на качестве контрольной
группы. Прежний контроль («соседние блюда той же категории в той же точке»)
провалился по трём пунктам сразу:

  1. Соседнее блюдо — конкурент. Подняли цену торта А, часть спроса ушла на Б.
     Значит Б задет нашим же решением и не может изображать «что было бы, если
     бы мы ничего не делали».
  2. В кондитерской хвост ассортимента крутится: из 34 «контрольных» тортов 21
     во втором окне не продался ни разу, 7 появились только там. Их «падение
     на 11%» — ротация выпечки, а не спрос.
  3. 111 штук за две недели на 34 позиции: собственный шум контроля больше
     измеряемого эффекта.

Итог: контроль давал +261 531 ₸ там, где корректный расчёт даёт −41 113 ₸.

Здесь реализован контроль «тот же товар в других точках той же концепции»:
  * тот же SKU — значит тот же сезон, та же рецептура, тот же жизненный цикл;
  * другая точка — наше решение туда не дотянулось;
  * объём в разы больше (3 229 шт против 520 у пилота).

Сравнение трёхслойное:
    позиция у нас ÷ тот же товар по сети ÷ наша точка целиком по сети
Третий слой нужен, чтобы слабый месяц у самой точки не записался в минус
решению о цене.

Неопределённость считается перетасовкой дней (bootstrap): дни окна случайно
пересобираются и эффект пересчитывается B раз. Формулы Пуассона тут врут —
продажи торта не ровный поток, в них сидят выходные, зарплатные дни и погода;
перетасовка реальных дней ловит это сама.

Пачка решений (один приказ по точке) считается СОВМЕСТНО: у позиций общие дни,
их ошибки скоррелированы, поэтому интервал по пачке нельзя получить сложением
интервалов позиций — гоняем одну перетасовку сразу по всем позициям приказа.

Концепции (Madlen — кофейни с тортами, Sandyq — рестораны с блюдами) живут в
разных iiko-доменах. Контроль и сетевой тренд считаются ТОЛЬКО внутри своего
домена: динамика ресторанов не годится в опору для кофейни.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Ворота качества: ниже этих порогов эффект не оценивается, а помечается
# «не измеримо». Ноль вместо оценки — ложь, отсутствие оценки — правда.
MIN_CONTROL_STORES = 3
MIN_CONTROL_QTY = 30.0          # штук в базовом окне по всей контрольной группе
BOOTSTRAP_DRAWS = 2000
CI_LEVEL = 0.90


@dataclass
class EffectResult:
    control_method: str = "none"          # cross_store | none
    measurable: bool = False
    reason: Optional[str] = None
    n_control_stores: int = 0
    control_qty_before: float = 0.0
    control_qty_after: float = 0.0
    control_trend: Optional[float] = None      # тренд товара по сети
    store_trend_adj: Optional[float] = None    # поправка на саму точку
    counterfactual_qty: Optional[float] = None
    effect_gp: Optional[float] = None
    ci_low: Optional[float] = None
    ci_high: Optional[float] = None
    p_negative: Optional[float] = None


@dataclass
class Panel:
    """Дневные ряды одной позиции — всё, что нужно для пересчёта на любых днях.

    Индексы: i — по рабочим дням точки, j — по календарным дням окна (контроль
    агрегирован по многим точкам, поэтому «рабочий день» у него не один).
    """
    old_price: float
    new_price: float
    cogs: float
    pilot_qty_b: np.ndarray
    pilot_qty_a: np.ndarray
    pilot_rev_a: np.ndarray
    pilot_tot_b: np.ndarray      # общий оборот точки, шт — для поправки на точку
    pilot_tot_a: np.ndarray
    ctl_qty_b: np.ndarray
    ctl_qty_a: np.ndarray
    ctl_sd_b: np.ndarray         # сколько контрольных точек работало в этот день
    ctl_sd_a: np.ndarray
    ctl_tot_b: np.ndarray
    ctl_tot_a: np.ndarray
    n_control_stores: int
    # даты нужны, чтобы показать ряды на графике: без них панель — набор
    # безымянных чисел, и «факт против контрфакта» нарисовать нечем
    dates_pilot_b: list[date]
    dates_pilot_a: list[date]
    dates_cal_b: list[date]
    dates_cal_a: list[date]


def _safe_div(num, den):
    """Деление с нулями: где знаменатель пуст — NaN, а не бесконечность."""
    num = np.asarray(num, dtype=float)
    den = np.asarray(den, dtype=float)
    out = np.full(np.broadcast(num, den).shape, np.nan, dtype=float)
    np.divide(num, den, out=out, where=den > 0)
    return out


def effect_of(panel: Panel, ib, ia, jb, ja):
    """Эффект в ₸ для набора индексов дней. Работает и на (B, n) — векторно.

    Возвращает (effect, counterfactual_qty, product_trend, store_adj).
    """
    n_b, n_a = np.shape(ib)[-1], np.shape(ia)[-1]

    rate_b = panel.pilot_qty_b[ib].sum(-1) / n_b
    qty_a = panel.pilot_qty_a[ia].sum(-1)
    rev_a = panel.pilot_rev_a[ia].sum(-1)

    # тренд товара по другим точкам, в расчёте на точко-день
    trend = _safe_div(
        _safe_div(panel.ctl_qty_a[ja].sum(-1), panel.ctl_sd_a[ja].sum(-1)),
        _safe_div(panel.ctl_qty_b[jb].sum(-1), panel.ctl_sd_b[jb].sum(-1)),
    )
    # как двигалась сама точка против сети
    store = _safe_div(
        _safe_div(panel.pilot_tot_a[ia].sum(-1) / n_a, panel.pilot_tot_b[ib].sum(-1) / n_b),
        _safe_div(
            _safe_div(panel.ctl_tot_a[ja].sum(-1), panel.ctl_sd_a[ja].sum(-1)),
            _safe_div(panel.ctl_tot_b[jb].sum(-1), panel.ctl_sd_b[jb].sum(-1)),
        ),
    )

    cf_qty = rate_b * trend * store * n_a
    effect = (rev_a - panel.cogs * qty_a) - cf_qty * (panel.old_price - panel.cogs)
    return effect, cf_qty, trend, store


class NetworkContext:
    """Общие для концепции ряды: кто когда работал и сколько всего продал.

    Грузится один раз на (домен, окно) и переиспользуется всеми позициями
    прогона — иначе на сотне рекомендаций был бы шторм одинаковых запросов.
    """

    def __init__(self, db: Session, domain: str, dfrom: date, dto: date):
        rows = db.execute(
            text("""
                SELECT s.department_id::text, s.sale_date, SUM(s.total_qty)
                FROM sku_daily_sales s
                JOIN departments d ON d.id = s.department_id
                WHERE d.iiko_source_domain = :domain
                  AND s.sale_date BETWEEN :dfrom AND :dto
                GROUP BY 1, 2
            """),
            {"domain": domain, "dfrom": dfrom, "dto": dto},
        ).fetchall()

        self.domain = domain
        self.total: dict[tuple[str, date], float] = {}
        self.open_days: dict[str, set[date]] = {}
        for dept, day, qty in rows:
            self.total[(dept, day)] = float(qty or 0.0)
            self.open_days.setdefault(dept, set()).add(day)

    def days_open(self, dept: str, days: list[date]) -> list[date]:
        opened = self.open_days.get(dept, set())
        return [d for d in days if d in opened]

    def store_days(self, depts: set[str], days: list[date]) -> np.ndarray:
        return np.array([sum(1 for s in depts if d in self.open_days.get(s, ()))
                         for d in days], dtype=float)

    def totals(self, depts: set[str], days: list[date]) -> np.ndarray:
        return np.array([sum(self.total.get((s, d), 0.0) for s in depts)
                         for d in days], dtype=float)


def _days(a: date, b: date) -> list[date]:
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


class PriceEffectEstimator:
    def __init__(self, db: Session, draws: int = BOOTSTRAP_DRAWS, seed: int = 20260805):
        self.db = db
        self.draws = draws
        self.rng = np.random.default_rng(seed)
        self._ctx: dict[tuple[str, date, date], NetworkContext] = {}
        self._domain: dict[str, Optional[str]] = {}

    # -- контекст --------------------------------------------------------

    def domain_of(self, dept_id: str) -> Optional[str]:
        if dept_id not in self._domain:
            self._domain[dept_id] = self.db.execute(
                text("SELECT iiko_source_domain FROM departments WHERE id = CAST(:d AS uuid)"),
                {"d": dept_id},
            ).scalar()
        return self._domain[dept_id]

    def context(self, dept_id: str, dfrom: date, dto: date) -> Optional[NetworkContext]:
        domain = self.domain_of(dept_id)
        if not domain:
            return None
        key = (domain, dfrom, dto)
        if key not in self._ctx:
            self._ctx[key] = NetworkContext(self.db, domain, dfrom, dto)
        return self._ctx[key]

    # -- сбор рядов ------------------------------------------------------

    def _control_stores(self, product_id: int, dept_id: str, domain: str,
                        dfrom: date, dto: date) -> set[str]:
        """Точки той же концепции, которые возят товар и НЕ меняли на него цену.

        Цены меняются по каждой точке отдельно (массового раската нет), поэтому
        контроль почти всегда есть. Но если приказ всё-таки прошёл по многим
        точкам сразу, исключение по sku_catalog_price оставит группу пустой —
        и оценка честно пометится «не измеримо», а не соврёт.
        """
        rows = self.db.execute(
            text("""
                WITH carriers AS (
                    SELECT DISTINCT s.department_id::text AS dept
                    FROM sku_daily_sales s
                    JOIN departments d ON d.id = s.department_id
                    WHERE s.product_id = :pid
                      AND d.iiko_source_domain = :domain
                      AND s.department_id <> CAST(:dept AS uuid)
                      AND s.sale_date BETWEEN :dfrom AND :dto
                ),
                repriced AS (
                    SELECT DISTINCT department_id::text AS dept
                    FROM sku_catalog_price
                    WHERE product_id = :pid
                      AND date_from BETWEEN :dfrom AND :dto
                      AND NOT is_stale
                )
                SELECT dept FROM carriers WHERE dept NOT IN (SELECT dept FROM repriced)
            """),
            {"pid": product_id, "dept": dept_id, "domain": domain,
             "dfrom": dfrom, "dto": dto},
        ).fetchall()
        return {r[0] for r in rows}

    def _series(self, product_id: int, depts: set[str], dfrom: date, dto: date):
        if not depts:
            return {}
        rows = self.db.execute(
            text("""
                SELECT department_id::text, sale_date, SUM(total_qty), SUM(total_sum)
                FROM sku_daily_sales
                WHERE product_id = :pid
                  AND department_id = ANY(CAST(:depts AS uuid[]))
                  AND sale_date BETWEEN :dfrom AND :dto
                GROUP BY 1, 2
            """),
            {"pid": product_id, "depts": list(depts), "dfrom": dfrom, "dto": dto},
        ).fetchall()
        return {(r[0], r[1]): (float(r[2] or 0), float(r[3] or 0)) for r in rows}

    # -- построение панели -----------------------------------------------

    def build_panel(self, product_id: int, dept_id: str, old_price: float,
                    new_price: float, cogs: float,
                    baseline_from: date, baseline_to: date,
                    eval_from: date, eval_to: date) -> tuple[Optional[Panel], EffectResult]:
        """Собрать ряды позиции. Второй элемент — результат с причиной отказа."""
        ctx = self.context(dept_id, baseline_from, eval_to)
        if ctx is None:
            return None, EffectResult(reason="не определена концепция точки")

        cal_b, cal_a = _days(baseline_from, baseline_to), _days(eval_from, eval_to)
        days_b = ctx.days_open(dept_id, cal_b)
        days_a = ctx.days_open(dept_id, cal_a)
        if not days_b or not days_a:
            return None, EffectResult(reason="точка не работала в одном из окон")

        pilot = self._series(product_id, {dept_id}, baseline_from, eval_to)
        pilot_qty_b = np.array([pilot.get((dept_id, d), (0.0, 0.0))[0] for d in days_b])
        if pilot_qty_b.sum() <= 0:
            return None, EffectResult(reason="позиция не продавалась до изменения")

        control = self._control_stores(product_id, dept_id, ctx.domain,
                                       baseline_from, eval_to)
        if len(control) < MIN_CONTROL_STORES:
            return None, EffectResult(
                reason=f"контрольных точек {len(control)} < {MIN_CONTROL_STORES}",
                n_control_stores=len(control))

        ctl = self._series(product_id, control, baseline_from, eval_to)
        ctl_qty_b = np.array([sum(ctl.get((s, d), (0.0, 0.0))[0] for s in control) for d in cal_b])
        ctl_qty_a = np.array([sum(ctl.get((s, d), (0.0, 0.0))[0] for s in control) for d in cal_a])
        if ctl_qty_b.sum() < MIN_CONTROL_QTY:
            return None, EffectResult(
                reason=f"контроль {ctl_qty_b.sum():.0f} шт < {MIN_CONTROL_QTY:.0f}",
                n_control_stores=len(control),
                control_qty_before=float(ctl_qty_b.sum()),
                control_qty_after=float(ctl_qty_a.sum()))

        panel = Panel(
            old_price=old_price, new_price=new_price, cogs=cogs,
            pilot_qty_b=pilot_qty_b,
            pilot_qty_a=np.array([pilot.get((dept_id, d), (0.0, 0.0))[0] for d in days_a]),
            pilot_rev_a=np.array([pilot.get((dept_id, d), (0.0, 0.0))[1] for d in days_a]),
            pilot_tot_b=ctx.totals({dept_id}, days_b),
            pilot_tot_a=ctx.totals({dept_id}, days_a),
            ctl_qty_b=ctl_qty_b, ctl_qty_a=ctl_qty_a,
            ctl_sd_b=ctx.store_days(control, cal_b),
            ctl_sd_a=ctx.store_days(control, cal_a),
            ctl_tot_b=ctx.totals(control, cal_b),
            ctl_tot_a=ctx.totals(control, cal_a),
            n_control_stores=len(control),
            dates_pilot_b=days_b, dates_pilot_a=days_a,
            dates_cal_b=cal_b, dates_cal_a=cal_a,
        )
        return panel, EffectResult(
            control_method="cross_store", measurable=True,
            n_control_stores=len(control),
            control_qty_before=float(ctl_qty_b.sum()),
            control_qty_after=float(ctl_qty_a.sum()))

    # -- перетасовка дней ------------------------------------------------

    def _draws_for(self, n_pb: int, n_pa: int, n_cb: int, n_ca: int):
        B = self.draws
        r = self.rng
        return (r.integers(0, n_pb, size=(B, n_pb)), r.integers(0, n_pa, size=(B, n_pa)),
                r.integers(0, n_cb, size=(B, n_cb)), r.integers(0, n_ca, size=(B, n_ca)))

    @staticmethod
    def _interval(samples: np.ndarray, need: int):
        samples = samples[np.isfinite(samples)]
        if samples.size < need:
            return None, None, None
        tail = (1.0 - CI_LEVEL) / 2.0
        lo, hi = np.quantile(samples, [tail, 1.0 - tail])
        return float(lo), float(hi), float((samples < 0).mean())

    # -- оценка одной позиции --------------------------------------------

    def estimate(self, product_id: int, dept_id: str, old_price: float,
                 new_price: float, cogs: float, baseline_from: date,
                 baseline_to: date, eval_from: date,
                 eval_to: date) -> tuple[EffectResult, Optional[Panel]]:
        """Возвращает (результат, панель). Панель нужна вызывающему, чтобы
        посчитать пачку решений совместно, не собирая ряды повторно."""
        panel, res = self.build_panel(product_id, dept_id, old_price, new_price,
                                      cogs, baseline_from, baseline_to,
                                      eval_from, eval_to)
        if panel is None:
            return res, None

        full = lambda a: np.arange(len(a))
        point, cf, trend, store = effect_of(
            panel, full(panel.pilot_qty_b), full(panel.pilot_qty_a),
            full(panel.ctl_qty_b), full(panel.ctl_qty_a))
        if not np.isfinite(point):
            return EffectResult(control_method="cross_store", measurable=False,
                                reason="не удалось построить контрфакт",
                                n_control_stores=panel.n_control_stores,
                                control_qty_before=res.control_qty_before,
                                control_qty_after=res.control_qty_after), None

        samples, *_ = effect_of(panel, *self._draws_for(
            len(panel.pilot_qty_b), len(panel.pilot_qty_a),
            len(panel.ctl_qty_b), len(panel.ctl_qty_a)))
        lo, hi, p_neg = self._interval(samples, self.draws // 2)

        res.control_trend = float(trend)
        res.store_trend_adj = float(store)
        res.counterfactual_qty = float(cf)
        res.effect_gp = float(point)
        res.ci_low, res.ci_high, res.p_negative = lo, hi, p_neg
        return res, panel

    # -- дневная раскладка для графика -----------------------------------

    @staticmethod
    def daily_breakdown(panel: Panel) -> list[dict]:
        """Ряды «факт против контрфакта» по дням.

        Контрфакт распределяется по дням окна пропорционально дневному ритму
        контрольной группы, а не ровной полкой: у выпечки будни и выходные
        отличаются вдвое, и ровная линия выглядела бы как систематический
        промах там, где его нет. Сумма по дням в точности равна оконному
        контрфакту — тому же числу, что идёт в расчёт эффекта.
        """
        n_b = len(panel.dates_pilot_b)
        n_a = len(panel.dates_pilot_a)
        if n_b == 0 or n_a == 0:
            return []

        rate_before = panel.pilot_qty_b.sum() / n_b
        ctl_rate_b = _safe_div(panel.ctl_qty_b, panel.ctl_sd_b)
        ctl_rate_a = _safe_div(panel.ctl_qty_a, panel.ctl_sd_a)
        base_mean = np.nanmean(ctl_rate_b) if np.isfinite(ctl_rate_b).any() else np.nan

        _, cf_total, _, store = effect_of(
            panel, np.arange(n_b), np.arange(n_a),
            np.arange(len(panel.ctl_qty_b)), np.arange(len(panel.ctl_qty_a)))

        pilot_a = dict(zip(panel.dates_pilot_a, panel.pilot_qty_a))
        ctl_shape = dict(zip(panel.dates_cal_a, ctl_rate_a))

        rows: list[dict] = []
        for d, qty in zip(panel.dates_pilot_b, panel.pilot_qty_b):
            rows.append({"date": str(d), "phase": "before", "qty": float(qty),
                         "counterfactual": None})

        for d in panel.dates_pilot_a:
            shape = ctl_shape.get(d, np.nan)
            if np.isfinite(base_mean) and base_mean > 0 and np.isfinite(shape):
                cf = rate_before * float(store) * (shape / base_mean)
            else:
                cf = float(cf_total) / n_a
            rows.append({"date": str(d), "phase": "after",
                         "qty": float(pilot_a.get(d, 0.0)),
                         "counterfactual": round(float(cf), 3)})

        # округление по дням не должно расходиться с оконным контрфактом
        after = [r for r in rows if r["phase"] == "after"]
        drift = float(cf_total) - sum(r["counterfactual"] for r in after)
        if after and abs(drift) > 1e-6:
            after[-1]["counterfactual"] = round(after[-1]["counterfactual"] + drift, 3)

        return rows

    # -- оценка пачки решений --------------------------------------------

    def estimate_batch(self, panels: list[Panel]) -> EffectResult:
        """Совместная оценка приказа: одна перетасовка дней на все позиции.

        Складывать интервалы позиций нельзя — дни у них общие, а значит ошибки
        скоррелированы, и сумма независимых интервалов вышла бы уже реального.
        """
        if not panels:
            return EffectResult(reason="в пачке нет измеримых позиций")

        full = lambda a: np.arange(len(a))
        point = 0.0
        for p in panels:
            e, *_ = effect_of(p, full(p.pilot_qty_b), full(p.pilot_qty_a),
                              full(p.ctl_qty_b), full(p.ctl_qty_a))
            if np.isfinite(e):
                point += float(e)

        # дни в пачке общие: у всех позиций одна точка и одно окно
        ref = panels[0]
        ib, ia, jb, ja = self._draws_for(
            len(ref.pilot_qty_b), len(ref.pilot_qty_a),
            len(ref.ctl_qty_b), len(ref.ctl_qty_a))

        total = np.zeros(self.draws, dtype=float)
        for p in panels:
            e, *_ = effect_of(p, ib, ia, jb, ja)
            total += np.nan_to_num(e, nan=0.0)

        lo, hi, p_neg = self._interval(total, self.draws // 2)
        return EffectResult(
            control_method="cross_store", measurable=True,
            n_control_stores=max(p.n_control_stores for p in panels),
            effect_gp=point, ci_low=lo, ci_high=hi, p_negative=p_neg)
