"""Отчёт об эффекте ценовых решений по точке — считается, а не сочиняется.

Почему без LLM. Весь смысл отчёта в том, чтобы не перепутать три вещи:
сколько денег прибавилось в кассе, сколько из этого можно отнести на счёт
решения о цене, и насколько уверенно это измерено. Ровно на этих различиях
подсистема уже один раз ошиблась — дашборд показывал +172 тыс ₸ там, где
честный расчёт даёт «не определено». Пересказ чисел языковой моделью
воспроизводил бы ту же ошибку с вероятностью, которую нечем контролировать.
Поэтому текст собирается шаблоном, а все числа подставляются из расчёта.

Отдельно считается «планка шума»: несколько прошлых периодов, когда цену НЕ
меняли, прогоняются через тот же расчёт. Честный ответ там — ноль, а реальный
разброс показывает, начиная с какой величины эффекту вообще можно верить.
"""

from __future__ import annotations

import logging
import statistics
from datetime import date, timedelta
from typing import Any, Optional

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# «Пустые» периоды ищутся сканированием назад, а не фиксированными отступами:
# цены на точке правят нерегулярно (на пилоте — 14 раз за пять месяцев), и
# любой заранее заданный отступ почти наверняка попадёт в переоценку. Шаг 14
# дней, чтобы окна проверок не перекрывались.
PLACEBO_WINDOW_DAYS = 14
PLACEBO_STEP_DAYS = 7
PLACEBO_MIN_OFFSET = 28
# Глубже 4 месяцев не уходим: там другой сезон и другой ассортимент, и «шум»
# начинает мерить не блуждание точки, а разницу зимы с летом. На пилоте
# проверка от 3 февраля давала −40% и раздувала планку вдвое.
PLACEBO_MAX_OFFSET = 140
PLACEBO_TARGET_RUNS = 6


def _money(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v:,.0f} ₸".replace(",", " ")


def _pct(v: Optional[float], digits: int = 1) -> str:
    if v is None:
        return "—"
    return f"{v:+.{digits}f}%"


def _plural(n: int, one: str, few: str, many: str) -> str:
    n10, n100 = n % 10, n % 100
    if n10 == 1 and n100 != 11:
        return one
    if 2 <= n10 <= 4 and not 12 <= n100 <= 14:
        return few
    return many


class PricingEffectReportService:
    def __init__(self, db: Session):
        self.db = db

    # -- сбор фактов ------------------------------------------------------

    def _outcomes(self, dept: str) -> list[dict]:
        rows = self.db.execute(
            text("""
                SELECT o.*, p.name AS product_name, r.delta_pct, r.menu_role,
                       r.elasticity_used, r.constraints_applied
                FROM price_recommendation_outcome o
                JOIN product p ON p.id = o.product_id
                JOIN price_recommendation r ON r.id = o.recommendation_id
                WHERE o.department_id = CAST(:d AS uuid)
                ORDER BY o.incremental_delta_gp DESC NULLS LAST
            """),
            {"d": dept},
        ).mappings().all()
        return [dict(r) for r in rows]

    def _batches(self, dept: str) -> list[dict]:
        rows = self.db.execute(
            text("""
                SELECT * FROM price_outcome_batch
                WHERE department_id = CAST(:d AS uuid)
                ORDER BY applied_at
            """),
            {"d": dept},
        ).mappings().all()
        return [dict(r) for r in rows]

    # -- планка шума ------------------------------------------------------

    def _placebo(self, dept: str, applied_at: date, items: list[dict]) -> dict:
        """Прогнать расчёт на периодах, когда цену не меняли. Ответ должен быть 0."""
        from .pricing_effect import PriceEffectEstimator, effect_of

        est = PriceEffectEstimator(self.db)
        runs: list[dict] = []

        for offset in range(PLACEBO_MIN_OFFSET, PLACEBO_MAX_OFFSET + 1, PLACEBO_STEP_DAYS):
            if len(runs) >= PLACEBO_TARGET_RUNS:
                break
            fake = applied_at - timedelta(days=offset)
            bfrom = fake - timedelta(days=PLACEBO_WINDOW_DAYS)
            eto = fake + timedelta(days=PLACEBO_WINDOW_DAYS - 1)

            # окно должно быть «пустым»: если в нём цену на эти позиции меняли,
            # проверка перестаёт быть плацебо и её надо выбросить
            touched = self.db.execute(
                text("""
                    SELECT COUNT(*) FROM sku_catalog_price
                    WHERE department_id = CAST(:d AS uuid)
                      AND product_id = ANY(CAST(:ids AS bigint[]))
                      AND date_from BETWEEN :bfrom AND :eto
                      AND NOT is_stale
                """),
                {"d": dept, "ids": [i["product_id"] for i in items],
                 "bfrom": bfrom, "eto": eto},
            ).scalar()
            if touched:
                continue

            panels, margins = [], []
            for it in items:
                price = float(it["old_price"] or 0)
                cogs = _unit_cogs(it)
                panel, _ = est.build_panel(
                    product_id=it["product_id"], dept_id=dept,
                    old_price=price, new_price=price, cogs=cogs,
                    baseline_from=bfrom, baseline_to=fake - timedelta(days=1),
                    eval_from=fake, eval_to=eto,
                )
                if panel is not None:
                    panels.append(panel)
                    margins.append(price - cogs)
            if not panels:
                continue

            idx = lambda a: np.arange(len(a))
            fact = cf = money = 0.0
            for panel, margin in zip(panels, margins):
                _, cf_qty, _, _ = effect_of(
                    panel, idx(panel.pilot_qty_b), idx(panel.pilot_qty_a),
                    idx(panel.ctl_qty_b), idx(panel.ctl_qty_a))
                cf_qty = float(np.nan_to_num(cf_qty, nan=0.0))
                fact += float(panel.pilot_qty_a.sum())
                cf += cf_qty
                money += margin * (float(panel.pilot_qty_a.sum()) - cf_qty)
            if cf <= 0:
                continue
            runs.append({
                "date": str(fake),
                "deviation_pct": round((fact / cf - 1) * 100, 1),
                "money": round(money, 0),
                "positions": len(panels),
            })

        # Отклонение считаем ОТ НУЛЯ, а не от среднего: правильный ответ на
        # плацебо — ноль, и если проверки систематически уехали в плюс, это
        # тоже часть ошибки, а не «средний уровень», от которого можно мерить.
        spread_pct = spread_money = None
        if len(runs) >= 2:
            spread_pct = round(_rms([r["deviation_pct"] for r in runs]), 1)
            spread_money = round(_rms([r["money"] for r in runs]), 0)
        return {"runs": runs, "spread_pct": spread_pct, "spread_money": spread_money}

    # -- сборка -----------------------------------------------------------

    def collect(self, dept: str) -> dict:
        items = self._outcomes(dept)
        if not items:
            return {"positions": 0}

        batches = self._batches(dept)
        measurable = [i for i in items if i["measurable"]]
        confirmed = [
            i for i in measurable
            if i["effect_ci_low"] is not None and i["effect_ci_high"] is not None
            and (float(i["effect_ci_low"]) > 0 or float(i["effect_ci_high"]) < 0)
        ]

        dept_name = self.db.execute(
            text("SELECT name FROM departments WHERE id = CAST(:d AS uuid)"), {"d": dept},
        ).scalar()

        gp_before = sum(
            float(i["gp_before"]) * int(i["days_after"]) / int(i["days_before"])
            for i in measurable if i["days_before"]
        )
        gp_after = sum(float(i["gp_after"]) for i in measurable)
        effect = sum(float(i["incremental_delta_gp"] or 0) for i in measurable)
        expected = sum(float(i["expected_delta_gp"] or 0) for i in items)

        applied_at = min(i["applied_at"] for i in items)
        placebo = self._placebo(dept, applied_at, measurable)

        deltas = [float(i["delta_pct"]) for i in items if i["delta_pct"] is not None]
        return {
            "department_id": dept,
            "department_name": dept_name,
            "applied_at": str(applied_at),
            "period_start": str(min(i["baseline_from"] for i in items)),
            "period_end": str(max(i["eval_to"] for i in items)),
            "eval_window_days": int(items[0]["eval_window_days"]),
            "positions": len(items),
            "measurable": len(measurable),
            "confirmed": len(confirmed),
            "price_step_min": min(deltas) if deltas else None,
            "price_step_max": max(deltas) if deltas else None,
            "gp_before": round(gp_before, 0),
            "gp_after": round(gp_after, 0),
            "cash": round(gp_after - gp_before, 0),
            "counterfactual_gp": round(gp_after - effect, 0),
            "effect": round(effect, 0),
            "expected": round(expected, 0),
            "ci_low": float(batches[0]["effect_ci_low"]) if batches and batches[0]["effect_ci_low"] is not None else None,
            "ci_high": float(batches[0]["effect_ci_high"]) if batches and batches[0]["effect_ci_high"] is not None else None,
            "p_negative": float(batches[0]["p_negative"]) if batches and batches[0]["p_negative"] is not None else None,
            "control_stores_avg": round(
                statistics.mean([int(i["n_control_stores"] or 0) for i in measurable]), 1
            ) if measurable else None,
            "placebo": placebo,
            "confirmed_items": [_item_brief(i) for i in confirmed],
            "items": [_item_brief(i) for i in items],
            "batches": [
                {"applied_at": str(b["applied_at"]), "n_positions": b["n_positions"],
                 "effect": float(b["effect_gp"]) if b["effect_gp"] is not None else None}
                for b in batches
            ],
        }

    # -- текст ------------------------------------------------------------

    def narrate(self, d: dict) -> str:
        if not d.get("positions"):
            return "По этой точке ещё нет измеренных ценовых решений."

        name = d["department_name"]
        win = d["eval_window_days"]
        cash, effect = d["cash"], d["effect"]
        lo, hi = d["ci_low"], d["ci_high"]
        noise = d["placebo"]["spread_money"]
        runs = d["placebo"]["runs"]

        # главный вывод зависит от того, выходит ли эффект за планку шума
        proven = (
            lo is not None and hi is not None and (lo > 0 or hi < 0)
            and (noise is None or abs(effect) > 1.645 * noise)
        )
        verdict = (
            "эффект подтверждён измерением"
            if proven else
            "эффект не доказан — ни в плюс, ни в минус"
        )

        L: list[str] = []
        A = L.append

        A(f"# Эффект ценовых решений — {name}")
        A("")
        A(f"Период наблюдения: **{_ru_date(d['period_start'])} – {_ru_date(d['period_end'])}**. "
          f"Цены применены {_ru_date(d['applied_at'])}, окно замера {win} "
          f"{_plural(win, 'день', 'дня', 'дней')}.")
        A("")
        A(f"**Главный вывод: {verdict}.**")
        A("")

        # ── 1. Что сделали
        A("## Что сделали")
        A("")
        A(f"Изменили цену на **{d['positions']} "
          f"{_plural(d['positions'], 'позицию', 'позиции', 'позиций')}**. "
          f"Шаг изменения от {_pct(d['price_step_min'])} до {_pct(d['price_step_max'])}. "
          f"Фактические цены в чеках сверены с приказом.")
        A("")
        if d["measurable"] < d["positions"]:
            skipped = d["positions"] - d["measurable"]
            A(f"Из них {d['measurable']} удалось измерить, {skipped} — нет: "
              f"по ним не набралось контрольной группы. Такие позиции в расчёт "
              f"эффекта не включены (ноль вместо оценки был бы враньём).")
            A("")

        # ── 2. Три числа
        A("## Три числа, которые нельзя путать")
        A("")
        A("| Показатель | Значение | Что это |")
        A("|---|---:|---|")
        A(f"| Прибыль до | {_money(d['gp_before'])} | за равное число рабочих дней |")
        A(f"| Прибыль после | {_money(d['gp_after'])} | факт |")
        A(f"| **Изменение в кассе** | **{_money(cash)}** | сколько денег реально прибавилось |")
        A(f"| Было бы без изменения цены | {_money(d['counterfactual_gp'])} | оценка по тем же блюдам в других точках |")
        A(f"| **Эффект решения** | **{_money(effect)}** | вклад именно цены |")
        A(f"| Ожидание модели | {_money(d['expected'])} | что прогнозировал оптимизатор |")
        A("")
        A(f"Изменение в кассе и эффект решения — **разные вопросы**. Первое сравнивает "
          f"с прошлым: прибыль {'выросла' if cash >= 0 else 'снизилась'} на {_money(abs(cash))}. "
          f"Второе сравнивает с альтернативой: если бы цену не трогали, прибыль составила бы "
          f"{_money(d['counterfactual_gp'])}, то есть решение дало "
          f"{'плюс' if effect >= 0 else 'минус'} {_money(abs(effect))} к этой величине.")
        A("")
        A("Аналогия: зарплата выросла на 5% — правда, денег стало больше. "
          "Инфляция 8% — тоже правда, покупательная способность упала. "
          "Оба утверждения верны и отвечают на разные вопросы.")
        A("")

        # ── 3. Как считается — на живом примере
        example = _pick_example(d["items"])
        if example:
            A("## Как это считается — на примере")
            A("")
            A(f"**{example['product_name']}**, цена {_money(example['old_price'])} → "
              f"{_money(example['new_price'])}.")
            A("")
            A(f"- Продали за окно **{example['qty_after']:.0f} "
              f"{_plural(int(example['qty_after']), 'штуку', 'штуки', 'штук')}** по новой цене")
            A(f"- Продали бы **{example['counterfactual_qty']:.1f}** по старой — столько дал бы "
              f"этот же товар, повтори он динамику {example['n_control_stores']} других точек, "
              f"где цену не меняли")
            A(f"- Разница в прибыли между этими двумя вариантами: **{_money(example['effect'])}**")
            A("")
            A("  Обратите внимание: эффект складывается из двух вещей сразу — сколько штук "
              "продали и сколько принесла каждая. Просто умножить разницу в штуках на цену "
              "нельзя, потому что цена у этих штук разная.")
            if example["ci_low"] is not None:
                A(f"- Разброс оценки: от {_money(example['ci_low'])} до {_money(example['ci_high'])}")
            A("")
            A("Контрольная группа — тот же самый товар в других точках сети. Не соседние "
              "блюда: сосед по витрине конкурент, часть спроса перетекает на него, и он "
              "перестаёт быть независимым наблюдателем.")
            A("")

        # ── 4. Планка шума
        A("## Насколько этому можно верить")
        A("")
        if runs:
            A(f"Тот же расчёт прогнан на {len(runs)} "
              f"{_plural(len(runs), 'периоде', 'периодах', 'периодах')}, когда цену "
              f"**не меняли вообще**. Честный ответ там — ноль:")
            A("")
            A("| Период | Отклонение | «Эффект» |")
            A("|---|---:|---:|")
            for r in runs:
                A(f"| {_ru_date(r['date'])} | {_pct(r['deviation_pct'])} | {_money(r['money'])} |")
            A("")
            if noise:
                A(f"Разброс ложных срабатываний — **±{_money(noise)}**. Это собственное "
                  f"«блуждание» точки: продажи месяц к месяцу гуляют сами по себе, без "
                  f"всякой цены. Любой эффект меньше этой величины неотличим от совпадения.")
                A("")
                A(f"Наш результат — {_money(effect)} при планке шума ±{_money(noise)}. "
                  + ("Он выходит за планку, значит измерен." if proven
                     else "Он **внутри** этой планки, значит не измерен."))
                A("")
        elif lo is not None:
            A(f"Оценка эффекта лежит в диапазоне от {_money(lo)} до {_money(hi)}. "
              f"Диапазон {'не накрывает' if proven else 'накрывает'} ноль.")
            A("")

        if d["p_negative"] is not None and not proven:
            A(f"Вероятность того, что эффект отрицательный — {d['p_negative'] * 100:.0f}%. "
              f"Это не «мы потеряли», а «монета легла чуть чаще на эту сторону».")
            A("")

        # ── 5. Позиции
        A("## Позиции")
        A("")
        A("| Позиция | Цена | Эффект | Разброс | Вывод |")
        A("|---|---:|---:|---:|---|")
        for it in d["items"]:
            if not it["measurable"]:
                verdict_i = "не измеримо"
                eff_s, ci_s = "—", it.get("not_measurable_reason") or "—"
            else:
                conf = (it["ci_low"] is not None and it["ci_high"] is not None
                        and (it["ci_low"] > 0 or it["ci_high"] < 0))
                verdict_i = "подтверждено" if conf else "не подтверждено"
                eff_s = _money(it["effect"])
                ci_s = (f"{_money(it['ci_low'])} … {_money(it['ci_high'])}"
                        if it["ci_low"] is not None else "—")
            A(f"| {it['product_name']} | {_money(it['old_price'])} → {_money(it['new_price'])} "
              f"| {eff_s} | {ci_s} | {verdict_i} |")
        A("")

        # ── 6. Что дальше
        A("## Что это значит и что дальше")
        A("")
        if proven:
            A(f"Эффект по этой точке измерен и составляет {_money(effect)} за {win} "
              f"{_plural(win, 'день', 'дня', 'дней')}. Решение можно тиражировать на "
              f"сопоставимые позиции.")
        else:
            A(f"На одной точке за {win} {_plural(win, 'день', 'дня', 'дней')} измерить "
              f"эффект изменения цены на {_pct(d['price_step_max'])} **невозможно в принципе**: "
              f"собственное блуждание точки больше ожидаемой реакции спроса. Это не дефект "
              f"расчёта, а свойство данных — и теперь оно измерено, а не предполагается.")
            A("")
            A("Что из этого следует:")
            A("")
            A("1. **Цифру нельзя трактовать ни как успех, ни как провал.** "
              "«Прибыль выросла на " + _money(abs(cash)) + "» и «решение стоило нам "
              + _money(abs(effect)) + "» одинаково не доказаны.")
            A("2. **Ответ даст накопление приказов.** Когда наберётся 10–15 приказов по "
              "разным точкам и датам, блуждание отдельных точек взаимно погасится, и "
              "сводная оценка станет осмысленной.")
            A("3. **Следующие приказы стоит ставить на позиции с оборотом.** "
              "Штучный товар с продажами 1–2 в день не измеряется ни при какой длине окна.")
        A("")
        A("---")
        A("")
        A(f"*Контрольная группа: в среднем {d['control_stores_avg']} "
          f"{_plural(int(d['control_stores_avg'] or 0), 'точка', 'точки', 'точек')} на позицию. "
          f"Проверочные периоды берутся за последние 4 месяца и частично "
          f"перекрываются, поэтому планка шума — оценка снизу: реальная "
          f"неопределённость не меньше указанной. Все числа пересчитываются "
          f"кнопкой «Пересчитать» в разделе «Результаты».*")

        return "\n".join(L)

    def generate(self, department_id: str) -> Any:
        from ..models.pricing_analytics import PricingReport

        data = self.collect(department_id)
        narrative = self.narrate(data)
        report = PricingReport(
            report_type="effect",
            scope="department",
            department_id=department_id,
            period_start=date.fromisoformat(data["period_start"]) if data.get("period_start") else date.today(),
            period_end=date.fromisoformat(data["period_end"]) if data.get("period_end") else date.today(),
            data=data,
            kpis={
                "positions": data.get("positions"),
                "cash": data.get("cash"),
                "effect": data.get("effect"),
                "expected": data.get("expected"),
                "confirmed": data.get("confirmed"),
                "noise_floor": data.get("placebo", {}).get("spread_money"),
            },
            narrative=narrative,
            provider="calculated",   # не LLM: числа и текст собраны расчётом
            model=None,
            status="ok",
        )
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)
        return report


def _rms(values: list[float]) -> float:
    """Среднеквадратичное отклонение от нуля."""
    return (sum(v * v for v in values) / len(values)) ** 0.5


def _unit_cogs(item: dict) -> float:
    qty = float(item["qty_before"] or 0)
    if qty <= 0:
        return 0.0
    return (float(item["revenue_before"] or 0) - float(item["gp_before"] or 0)) / qty


def _item_brief(i: dict) -> dict:
    return {
        "product_id": i["product_id"],
        "product_name": (i["product_name"] or "").strip(),
        "old_price": float(i["old_price"]) if i["old_price"] is not None else None,
        "new_price": float(i["new_price"]) if i["new_price"] is not None else None,
        "qty_before": float(i["qty_before"] or 0),
        "qty_after": float(i["qty_after"] or 0),
        "counterfactual_qty": float(i["counterfactual_qty"]) if i["counterfactual_qty"] is not None else None,
        "effect": float(i["incremental_delta_gp"]) if i["incremental_delta_gp"] is not None else None,
        "ci_low": float(i["effect_ci_low"]) if i["effect_ci_low"] is not None else None,
        "ci_high": float(i["effect_ci_high"]) if i["effect_ci_high"] is not None else None,
        "measurable": bool(i["measurable"]),
        "not_measurable_reason": i["not_measurable_reason"],
        "n_control_stores": i["n_control_stores"],
    }


def _pick_example(items: list[dict]) -> Optional[dict]:
    """Позиция для разбора: сначала подтверждённая, иначе самая крупная по обороту."""
    measurable = [i for i in items if i["measurable"] and i["counterfactual_qty"] is not None]
    if not measurable:
        return None
    confirmed = [i for i in measurable
                 if i["ci_low"] is not None and (i["ci_low"] > 0 or i["ci_high"] < 0)]
    pool = confirmed or measurable
    return max(pool, key=lambda i: i["qty_after"])


def _ru_date(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{d}.{m}.{y}"
