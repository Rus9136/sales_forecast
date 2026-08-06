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
    """Минус — типографский (−), а не дефис: в тексте отчёта его иначе не видно."""
    if v is None:
        return "—"
    s = f"{abs(v):,.0f}".replace(",", " ")
    return f"−{s} ₸" if v < 0 else f"{s} ₸"


def _money_signed(v: Optional[float]) -> str:
    """Для величин, где направление — суть числа (эффект, ожидание)."""
    if v is None:
        return "—"
    s = f"{abs(v):,.0f}".replace(",", " ")
    return f"{'−' if v < 0 else '+'}{s} ₸"


def _pct(v: Optional[float], digits: int = 1) -> str:
    if v is None:
        return "—"
    return f"{v:+.{digits}f}%".replace("-", "−").replace(".", ",")


def _num(v: Optional[float], digits: int = 1) -> str:
    if v is None:
        return "—"
    return f"{v:.{digits}f}".replace(".", ",")


def _plural_num(v: Optional[float], one: str, few: str, many: str) -> str:
    """Дробное число тянет за собой родительный падеж: «13,5 точки», не «точек»."""
    if v is None:
        return many
    if float(v) != int(v):
        return few
    return _plural(int(v), one, few, many)


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
        """Отчёт для человека, который видит его впервые.

        Правило текста: ни одного термина без объяснения на месте, каждое
        число — с ответом на вопрос «и что это значит». Порядок изложения —
        как думает управляющий: что сделали → сколько денег → это из-за цены
        или само по себе → можно ли верить → что делать дальше.
        """
        if not d.get("positions"):
            return "По этой точке ещё не было изменений цен, которые можно было бы разобрать."

        name = d["department_name"]
        win = d["eval_window_days"]
        cash, effect = d["cash"], d["effect"]
        lo, hi = d["ci_low"], d["ci_high"]
        noise = d["placebo"]["spread_money"]
        runs = d["placebo"]["runs"]
        n = d["positions"]
        word = _direction_word(d)

        # результат считается доказанным, только если он и мимо нуля, и крупнее
        # обычных колебаний точки
        proven = (
            lo is not None and hi is not None and (lo > 0 or hi < 0)
            and (noise is None or abs(effect) > 1.645 * noise)
        )

        L: list[str] = []
        A = L.append

        A(f"# {word['title']} — {name}")
        A("")
        if proven:
            A(f"**Коротко: решение о цене сработало и принесло {_money(abs(effect))} "
              f"за {win} {_plural(win, 'день', 'дня', 'дней')}. Это не случайность — "
              f"проверено." if effect >= 0 else
              f"**Коротко: решение о цене обошлось нам в {_money(abs(effect))} "
              f"за {win} {_plural(win, 'день', 'дня', 'дней')}. Это не случайность — "
              f"проверено.")
            A("")
        else:
            A("**Коротко: заметного результата нет — ни в плюс, ни в минус.**")
            A("")
            A("Не потому, что цена ни на что не влияет, а потому, что влияние оказалось "
              "меньше обычных недельных колебаний точки. На таких весах его не видно. "
              "Ниже — по шагам, откуда это следует.")
            A("")

        # ── 1. Что сделали
        A("## Шаг 1. Что сделали")
        A("")
        step_lo, step_hi = abs(d["price_step_min"] or 0), abs(d["price_step_max"] or 0)
        A(f"{_ru_date(d['applied_at'])} {word['verb']} цены на **{n} "
          f"{_plural(n, 'позицию', 'позиции', 'позиций')}**. "
          f"Изменение небольшое — от {_num(step_lo)}% до {_num(step_hi)}%.")
        A("")

        # для примера берём самую ходовую позицию: на ней шаг цены нагляднее,
        # а разбор «как это считается» ниже идёт по подтверждённым
        example = _pick_volume_example(d["items"])
        if example and example["old_price"]:
            diff = (example["new_price"] or 0) - example["old_price"]
            A(f"Например, «{example['product_name']}» {word['was']} "
              f"{_money(example['old_price'])}, {word['became']} {_money(example['new_price'])} — "
              f"разница {_money(abs(diff))}.")
            A("")

        A(f"Дальше {win} {_plural(win, 'день', 'дня', 'дней')} "
          f"({_ru_date(d['applied_at'])} – {_ru_date(d['period_end'])}) смотрели, что стало "
          f"с продажами. Цены в чеках сверены с приказом — считаем по тому, что реально "
          f"пробили на кассе, а не по тому, что написано в приказе.")
        A("")
        if d["measurable"] < n:
            skipped = n - d["measurable"]
            A(f"Из {n} позиций посчитать удалось {d['measurable']}. "
              + (f"Одну — нет: её слишком мало продают, не с чем сравнивать. "
                 f"Ставить ей ноль было бы враньём, поэтому в итог она не входит."
                 if skipped == 1 else
                 f"Остальные {skipped} — нет: их слишком мало продают, не с чем "
                 f"сравнивать. Ставить им ноль было бы враньём, поэтому в итог они "
                 f"не входят."))
            A("")

        # ── 2. Денег в кассе
        A("## Шаг 2. Денег стало больше или меньше?")
        A("")
        A(f"Прибыль по этим позициям за {win} {_plural(win, 'день', 'дня', 'дней')} "
          f"**до** изменения — {_money(d['gp_before'])}, за столько же дней **после** — "
          f"{_money(d['gp_after'])}.")
        A("")
        A(f"### {'Стало больше' if cash >= 0 else 'Стало меньше'} на {_money(abs(cash))}")
        A("")
        A("Прибыль здесь — это выручка минус себестоимость продуктов. Аренда, зарплаты "
          "и прочие расходы в неё не входят.")
        A("")
        A("Но само по себе это ещё ничего не доказывает. За те же две недели в точку "
          "могло прийти больше гостей, могла быть жара, праздник или, наоборот, ремонт "
          "дороги рядом. Деньги выросли — а из-за чего, пока неизвестно.")
        A("")

        # ── 3. Заслуга цены
        A("## Шаг 3. А это вообще из-за цены?")
        A("")
        A(f"Чтобы отделить одно от другого, смотрим на **те же самые блюда в других "
          f"точках сети, где цену не меняли** — в среднем "
          f"{_num(d['control_stores_avg'])} "
          f"{_plural_num(d['control_stores_avg'], 'точка', 'точки', 'точек')} "
          f"на каждую позицию. Они показывают, что происходило бы у нас, если бы мы "
          f"ничего не трогали: тот же сезон, та же погода, та же мода на десерты.")
        A("")
        A(f"По ним выходит, что без изменения цены прибыль составила бы "
          f"**{_money(d['counterfactual_gp'])}**. Фактически получилось "
          f"{_money(d['gp_after'])}.")
        A("")
        A(f"### Заслуга самой цены — {_money_signed(effect)}")
        A("")
        A(f"Это и есть ответ на вопрос «что дало решение». Он не совпадает с цифрой "
          f"из шага 2 — и не должен: там мы сравнивали с прошлым ({_money_signed(cash)}), "
          f"здесь сравниваем с тем, что было бы без нашего вмешательства "
          f"({_money_signed(effect)}). Оба числа верные, просто отвечают на разные вопросы.")
        A("")
        if d["expected"]:
            A(f"Для сравнения: когда система предлагала эти цены, она рассчитывала на "
              f"{_money_signed(d['expected'])}.")
            A("")

        # ── 4. Погрешность
        A("## Шаг 4. Насколько этой цифре можно верить")
        A("")
        if runs and noise:
            A(f"Проверили так: взяли {len(runs)} прошлых "
              f"{_plural(len(runs), 'период', 'периода', 'периодов')}, когда цены "
              f"**вообще не трогали**, и прогнали ровно тот же расчёт. Правильный ответ "
              f"там — ноль, менять было нечего. Получилось вот что:")
            A("")
            A("| Двухнедельный период | Продажи против других точек | Расчёт показал «эффект» |")
            A("|---|---:|---:|")
            for r in runs:
                A(f"| с {_ru_date(r['date'])} | {_pct(r['deviation_pct'])} | {_money_signed(r['money'])} |")
            A("")
            A(f"Ни один из них не ноль. Это не ошибка расчёта — это значит, что продажи "
              f"точки сами по себе, без всяких цен, гуляют туда-сюда примерно на "
              f"**±{_money(noise)}** за две недели.")
            A("")
            A(f"### Наш результат — {_money_signed(effect)}. Погрешность измерения — ±{_money(noise)}")
            A("")
            if proven:
                A("Результат крупнее погрешности, значит его видно по-настоящему.")
            else:
                A("Результат **меньше** погрешности. Проще говоря: мы встали на весы "
                  "и увидели минус 300 граммов — но весы врут на килограмм. "
                  "Похудели мы или поправились, эти весы сказать не могут. "
                  "Ни цифра из шага 2, ни цифра из шага 3 пока ничего не доказывают.")
            A("")
        elif lo is not None:
            A(f"Расчёт даёт не одну точную цифру, а диапазон: от {_money(lo)} до {_money(hi)}. "
              + ("Ноль в него не попадает, значит результат реальный."
                 if proven else
                 "В этот диапазон попадает и ноль, и заметный плюс, и заметный минус — "
                 "то есть уверенно сказать нельзя ничего."))
            A("")

        if d["p_negative"] is not None and not proven:
            A(f"Если совсем упрощать: шансы, что решение сработало в минус — примерно "
              f"{d['p_negative'] * 100:.0f} из 100. Это ближе к подбрасыванию монетки, "
              f"чем к выводу.")
            A("")

        # ── 5. Разбор на одной позиции: показать механику на живом примере,
        # иначе «заслуга цены» остаётся для читателя магической цифрой
        conf_items = d.get("confirmed_items") or []
        A("## Шаг 5. Как это считается — на одной позиции")
        A("")
        show = conf_items or ([_pick_volume_example(d["items"])] if _pick_volume_example(d["items"]) else [])
        if conf_items:
            A(f"По {len(conf_items)} {_plural(len(conf_items), 'позиции', 'позициям', 'позициям')} "
              f"результат виден даже с учётом погрешности — на "
              f"{_plural(len(conf_items), 'ней', 'них', 'них')} и разберём:")
            A("")
        elif show:
            A("Ни одна позиция по отдельности из погрешности не выделяется — это "
              "ожидаемо, чем мельче срез, тем больше в нём шума. Но механику видно "
              "и на них, возьмём самую ходовую:")
            A("")
        for it in show:
            p_pilot, p_ctl = _growth(it)
            A(f"**{it['product_name']}** — цена {_money(it['old_price'])} → "
              f"{_money(it['new_price'])}, итог **{_money_signed(it['effect'])}**.")
            A("")
            A(f"- Продали {it['qty_after']:.0f} "
              f"{_plural(int(it['qty_after']), 'штуку', 'штуки', 'штук')}"
              + (f" — это {_pct(p_pilot, 0)} к прошлым двум неделям."
                 if p_pilot is not None else "."))
            if p_ctl is not None:
                A(f"- В других точках это же блюдо за то же время дало {_pct(p_ctl, 0)}. "
                  f"Значит, не трогай мы цену, у нас продалось бы примерно "
                  f"{it['counterfactual_qty']:.0f}, а не {it['qty_after']:.0f}.")
            A(f"- Разница в прибыли между этими двумя вариантами и есть "
              f"{_money_signed(it['effect'])}. Просто умножить разницу в штуках на цену "
              f"нельзя: часть штук продана по старой цене, часть по новой.")
            A("")
        A("Почему сравниваем именно с другими точками, а не с соседним блюдом на "
          "витрине: сосед — конкурент. Подорожал торт — часть гостей берёт соседний, "
          "и его продажи растут как раз из-за нашего же решения. Такой «свидетель» "
          "необъективен. А тот же торт в точке, где цену не трогали, о нашем приказе "
          "ничего не знает.")
        A("")

        # ── 6. Таблица позиций
        A("## Все позиции по порядку")
        A("")
        A("| Позиция | Цена | Продали: было → стало | Заслуга цены | Вывод |")
        A("|---|---:|---:|---:|---|")
        for it in d["items"]:
            qty = f"{it['qty_before']:.0f} → {it['qty_after']:.0f} шт"
            if not it["measurable"]:
                verdict_i = _plain_reason(it.get("not_measurable_reason"))
                eff_s = "—"
            else:
                conf = (it["ci_low"] is not None and it["ci_high"] is not None
                        and (it["ci_low"] > 0 or it["ci_high"] < 0))
                verdict_i = "видно точно" if conf else "в пределах погрешности"
                eff_s = _money_signed(it["effect"])
            A(f"| {it['product_name']} | {_money(it['old_price'])} → {_money(it['new_price'])} "
              f"| {qty} | {eff_s} | {verdict_i} |")
        A("")
        A("Как читать колонки: «продали» — штуки за две недели до и после. "
          "«Заслуга цены» — насколько прибыль отличается от того, что дали бы "
          "те же блюда в других точках. «В пределах погрешности» — цифра посчитана, "
          "но она мельче обычных колебаний, поэтому опираться на неё нельзя. "
          "Прочерк — посчитать не получилось, слишком мало продаж.")
        A("")

        # ── 7. Что дальше
        A("## Что делать дальше")
        A("")
        if proven:
            A(f"1. **Решение можно оставить.** Оно {'приносит' if effect >= 0 else 'стоит'} "
              f"{_money(abs(effect))} за {win} {_plural(win, 'день', 'дня', 'дней')}, "
              f"и это подтверждено, а не предположено.")
            A(f"2. **Можно повторить на похожих позициях** в других точках — с тем же "
              f"шагом цены и с таким же замером после.")
            A("3. **Замер продолжать.** Реакция гостя на цену не мгновенная: через "
              "месяц-два картина может измениться.")
        else:
            A(f"1. **Не делать выводов из этих цифр.** Ни «прибыль выросла на "
              f"{_money(abs(cash))}», ни «решение стоило нам {_money(abs(effect))}» "
              f"не доказаны. Правильный ответ сегодня — «пока не знаем».")
            A(f"2. **Копить приказы.** Одна точка за {win} "
              f"{_plural(win, 'день', 'дня', 'дней')} — слишком мало данных. "
              f"Когда наберётся 10–15 изменений по разным точкам и датам, случайные "
              f"колебания взаимно погасятся, и общая картина станет видна.")
            A("3. **Менять цену там, где есть оборот.** Товар, который продают "
              "по 1–2 штуки в день, не измерится никогда — ни за две недели, ни за два "
              "месяца. Позиции с десятками продаж в день дают ответ гораздо быстрее.")
            A(f"4. **Либо шаг крупнее.** Прибавка в {step_hi:.0f}% на этих объёмах "
              f"физически не поднимается над обычными колебаниями. Более крупный шаг "
              f"было бы видно — но это уже вопрос, готовы ли мы им рисковать.")
        A("")
        A("---")
        A("")
        A(f"*Отчёт собран расчётом по данным чеков, без участия ИИ. "
          f"Периоды для проверки берутся за последние 4 месяца и частично "
          f"накладываются друг на друга, поэтому реальная погрешность скорее "
          f"чуть больше указанной, чем меньше. Числа обновляются кнопкой "
          f"«Пересчитать» в разделе «Результаты».*")

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


def _direction_word(d: dict) -> dict:
    """Цены подняли, опустили или и то и другое — от этого зависят формулировки."""
    lo, hi = d.get("price_step_min"), d.get("price_step_max")
    if lo is not None and lo > 0:
        return {"title": "Что дало подорожание", "verb": "подняли",
                "was": "стоил", "became": "стал"}
    if hi is not None and hi < 0:
        return {"title": "Что дало снижение цен", "verb": "снизили",
                "was": "стоил", "became": "стал"}
    return {"title": "Что дало изменение цен", "verb": "изменили",
            "was": "стоил", "became": "стал"}


def _growth(it: dict) -> tuple[Optional[float], Optional[float]]:
    """Прирост продаж у нас и у контрольных точек, % к дням до изменения.

    Периоды «до» и «после» разной длины (до изменения цены может быть меньше
    рабочих дней), поэтому сравниваем не штуки, а штуки в пересчёте на равный срок.
    """
    qb = float(it.get("qty_before") or 0)
    db_, da = int(it.get("days_before") or 0), int(it.get("days_after") or 0)
    if qb <= 0 or db_ <= 0 or da <= 0:
        return None, None
    base = qb * da / db_
    pilot = (float(it["qty_after"]) / base - 1) * 100
    cf = it.get("counterfactual_qty")
    ctl = (float(cf) / base - 1) * 100 if cf is not None else None
    return pilot, ctl


def _plain_reason(reason: Optional[str]) -> str:
    """Техническая причина «не измеримо» → объяснение для человека."""
    if not reason:
        return "не удалось посчитать"
    r = reason.lower()
    if "контроль" in r:
        return "мало продаж, не с чем сравнить"
    if "прод" in r or "qty" in r:
        return "слишком мало продаж"
    return "не удалось посчитать"


def _item_brief(i: dict) -> dict:
    return {
        "product_id": i["product_id"],
        "days_before": int(i["days_before"]) if i["days_before"] is not None else None,
        "days_after": int(i["days_after"]) if i["days_after"] is not None else None,
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


def _pick_volume_example(items: list[dict]) -> Optional[dict]:
    """Самая ходовая измеримая позиция: на ней механика расчёта нагляднее всего."""
    measurable = [i for i in items if i["measurable"] and i["counterfactual_qty"] is not None]
    if not measurable:
        return None
    return max(measurable, key=lambda i: i["qty_after"])


def _ru_date(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{d}.{m}.{y}"
