"""B4: Configurable pricing rules with scope cascade."""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

VALID_RULE_TYPES = {
    "min_margin", "max_step", "min_frequency", "no_decrease_anchor",
    "min_competitive_idx", "rounding", "no_psychological", "stop_list",
    "max_changes_per_cycle", "effect_measurement",
}

# допустимые scope по типу правила: max_changes_per_cycle читается только
# get_change_cycle_cap (department/global) — segment/product-строки этого
# типа молча игнорировались бы. effect_measurement — только global: разные
# окна замера по точкам сделали бы результаты несравнимыми.
RULE_TYPE_SCOPES: dict[str, set[str]] = {
    "max_changes_per_cycle": {"global", "department"},
    "effect_measurement": {"global"},
}

# Границы окон замера. Меньше недели — день недели перекашивает сравнение;
# больше 90 дней — в период неизбежно попадают чужие переоценки, и
# контрольная группа выкашивается.
MEASUREMENT_LIMITS = {"eval_days": (7, 90), "baseline_days": (7, 90)}
VALID_SCOPE_TYPES = {"global", "segment", "department", "product"}

PREMIUM_ROLES = {"premium_anchor", "image_rare"}

# Fail-safe дефолты защитных правил: удаление строки правила из БД раньше
# МОЛЧА снимало проверку (check пропускал), при этом оптимизатор продолжал
# применять зашитые дефолты к сетке кандидатов — «система без правил» вела
# себя как «частично без ограничений». Теперь check при отсутствии строки
# применяет те же дефолты, что и генератор сетки.
FAILSAFE_DEFAULTS: dict[str, dict[str, Any]] = {
    "min_margin": {"value": 0.60},
    "max_step": {"value": 0.05},
    "min_frequency": {"days": 14},
    "rounding": {"step": 50, "flagship_step": 100},
    "effect_measurement": {"eval_days": 14, "baseline_days": 14},
}

# Откат (rec_type='rollback') возвращает цену, которая уже стояла в каталоге и
# отработала полное окно замера. К такому ходу неприменимы правила, которые
# описывают, КАК выбирать НОВУЮ цену:
#   * rounding — исходные цены пилота (430, 810, 1010, 1360, 1990, 2890 ₸) не
#     кратны шагу 50, и правило запрещало вернуться туда, откуда сама же
#     система и увела цену;
#   * max_step — шаг отката по построению равен исходному шагу; больше 5% он
#     выходит только там, где цену применили вручную с окончанием «90»;
#   * no_decrease_anchor / no_psychological — политика про якорные позиции
#     слабее доказанного убытка;
#   * min_frequency — outcome существует только после полного окна замера,
#     ждать ещё один интервал значит продолжать терять деньги.
# min_margin НЕ снимается: это финансовый пол, а не политика выбора цены.
# stop_list НЕ снимается: «не трогать» должно означать «не трогать» — чтобы
# разрешить откат, но запретить повышение, у правила есть params.block.
ROLLBACK_RELAXED_RULES = frozenset({
    "max_step", "rounding", "no_decrease_anchor", "no_psychological", "min_frequency",
})


def resolve_rounding_step(
    price: float, menu_role: Optional[str], rules: dict[str, dict[str, Any]],
) -> float:
    """Шаг округления цены. Единая точка: до этого логика была продублирована
    в check_recommendation и в _enumerate_candidates, и разъехаться им ничего
    не мешало.

    Плоский шаг 50 ₸ вырождает коридор на дешёвых позициях: у товара за 430 ₸
    интервал ±5% это 408.5…451.5, кратных пятидесяти внутри ровно одно — 450.
    Кандидат остаётся единственным, и, поскольку при |ε| < 1 прибыль монотонна
    по цене, он же и выбирается. Тонкой настройки на дешёвых позициях не
    существует, а это как раз импульсная выпечка — единственная группа с
    доказанным убытком от повышения.

    params.tiers (необязательно) задаёт шаг по цене:
        [{"max_price": 1500, "step": 10}, {"max_price": 5000, "step": 50},
         {"step": 100}]
    Без tiers поведение прежнее: step / flagship_step.
    """
    r = rules.get("rounding", FAILSAFE_DEFAULTS["rounding"])
    if menu_role in PREMIUM_ROLES:
        # у якорных позиций крупный шаг — часть ценового образа, не арифметика
        return float(r.get("flagship_step", 100))
    tiers = r.get("tiers")
    if isinstance(tiers, list) and tiers:
        for tier in tiers:
            cap = tier.get("max_price")
            if cap is None or price < float(cap):
                return float(tier.get("step", r.get("step", 50)))
    return float(r.get("step", 50))


class PricingRulesService:
    def __init__(self, db: Session):
        self.db = db

    def get_effective_rules(
        self,
        product_id: int,
        department_id: str,
        segment_type: Optional[str] = None,
    ) -> dict[str, dict[str, Any]]:
        """Resolve all rules for a SKU. Cascade: product → department → segment → global."""
        today = date.today()
        rows = self.db.execute(
            text("""
                SELECT rule_type, scope_type, scope_id, params
                FROM pricing_rule
                WHERE is_active = true
                  AND effective_from <= :today
                  AND (effective_to IS NULL OR effective_to >= :today)
                  AND (
                      (scope_type = 'global' AND scope_id IS NULL)
                      OR (scope_type = 'segment' AND scope_id = :segment)
                      OR (scope_type = 'department' AND scope_id = :dept_id)
                      OR (scope_type = 'product' AND scope_id = :product_id_str)
                  )
                ORDER BY
                    CASE scope_type
                        WHEN 'product' THEN 1
                        WHEN 'department' THEN 2
                        WHEN 'segment' THEN 3
                        WHEN 'global' THEN 4
                    END,
                    id
            """),
            {
                "today": today,
                "segment": segment_type or "",
                "dept_id": str(department_id),
                "product_id_str": str(product_id),
            },
        ).fetchall()

        effective: dict[str, dict[str, Any]] = {}
        for row in rows:
            if row[0] not in effective:
                effective[row[0]] = row[3]
        return effective

    def get_change_cycle_cap(self, department_id: str) -> Optional[dict[str, Any]]:
        """Portfolio-правило max_changes_per_cycle для точки (department > global).
        → {'value': N, 'window_days': D} или None, если правило не настроено."""
        today = date.today()
        row = self.db.execute(
            text("""
                SELECT params FROM pricing_rule
                WHERE rule_type = 'max_changes_per_cycle'
                  AND is_active = true
                  AND effective_from <= :today
                  AND (effective_to IS NULL OR effective_to >= :today)
                  AND (
                      (scope_type = 'department' AND scope_id = :dept_id)
                      OR (scope_type = 'global' AND scope_id IS NULL)
                  )
                ORDER BY CASE scope_type WHEN 'department' THEN 1 ELSE 2 END, id
                LIMIT 1
            """),
            {"today": today, "dept_id": str(department_id)},
        ).fetchone()
        if not row:
            return None
        params = row[0]
        return {
            "value": int(params.get("value", 15)),
            "window_days": int(params.get("window_days", 14)),
        }

    def get_measurement_window(self) -> dict[str, int]:
        """Окна замера эффекта: {'eval_days': N, 'baseline_days': M}.

        База и окно замера НЕ обязаны совпадать. Симметричное окно ломается на
        длинных горизонтах: база уезжает назад и захватывает чужие переоценки,
        после чего контрольные точки выкашиваются фильтром «цену не меняли».
        База должна стоять на тихом участке, окно замера — тянуться вперёд.
        """
        today = date.today()
        row = self.db.execute(
            text("""
                SELECT params FROM pricing_rule
                WHERE rule_type = 'effect_measurement'
                  AND scope_type = 'global' AND scope_id IS NULL
                  AND is_active = true
                  AND effective_from <= :today
                  AND (effective_to IS NULL OR effective_to >= :today)
                LIMIT 1
            """),
            {"today": today},
        ).fetchone()

        params = row[0] if row else FAILSAFE_DEFAULTS["effect_measurement"]
        out: dict[str, int] = {}
        for key, (lo, hi) in MEASUREMENT_LIMITS.items():
            default = FAILSAFE_DEFAULTS["effect_measurement"][key]
            try:
                value = int(params.get(key, default))
            except (TypeError, ValueError):
                value = default
            # выключенное или кривое правило не должно останавливать замер —
            # молча возвращаемся к дефолту, как и прочие fail-safe правила
            out[key] = min(max(value, lo), hi)
        return out

    def check_recommendation(
        self,
        current_price: float,
        candidate_price: float,
        cogs: Optional[float],
        menu_role: Optional[str],
        last_change_date: Optional[date],
        rules: dict[str, dict[str, Any]],
        rec_type: str = "optimizer",
    ) -> tuple[bool, list[str]]:
        """Check a candidate price against all rules. Returns (is_valid, violations).

        Для защитных правил (min_margin/max_step/min_frequency/rounding)
        отсутствие строки в БД НЕ отключает проверку — применяются
        FAILSAFE_DEFAULTS (fail-safe, а не fail-open).

        rec_type='rollback' снимает ROLLBACK_RELAXED_RULES — правила выбора
        НОВОЙ цены неприменимы к возврату цены, которая уже стояла. Список
        послаблений живёт здесь, а не в местах вызова: политика — забота
        сервиса правил.
        """
        violations: list[str] = []
        relaxed = ROLLBACK_RELAXED_RULES if rec_type == "rollback" else frozenset()

        # Rule 1: min_margin (fail-safe) — не снимается никогда
        r = rules.get("min_margin", FAILSAFE_DEFAULTS["min_margin"])
        if cogs is not None and candidate_price > 0:
            min_margin = r.get("value", 0.60)
            margin = (candidate_price - cogs) / candidate_price
            if margin < min_margin:
                violations.append(f"min_margin: {margin:.2%} < {min_margin:.0%}")

        # Rule 2: max_step (fail-safe)
        r = rules.get("max_step", FAILSAFE_DEFAULTS["max_step"])
        if "max_step" not in relaxed and current_price > 0:
            max_step = r.get("value", 0.05)
            step = abs(candidate_price - current_price) / current_price
            if step > max_step:
                violations.append(f"max_step: {step:.2%} > {max_step:.0%}")

        # Rule 3: min_frequency (fail-safe)
        r = rules.get("min_frequency", FAILSAFE_DEFAULTS["min_frequency"])
        if "min_frequency" not in relaxed and last_change_date:
            days_since = (date.today() - last_change_date).days
            min_days = r.get("days", 14)
            if days_since < min_days:
                violations.append(f"min_frequency: {days_since}d < {min_days}d")

        # Rule 4: no_decrease_anchor
        r = rules.get("no_decrease_anchor")
        if ("no_decrease_anchor" not in relaxed
                and r is not None and r.get("enabled", True)
                and menu_role == "premium_anchor"):
            if candidate_price < current_price:
                violations.append("no_decrease_anchor: price decrease on premium_anchor")

        # Rule 5: min_competitive_idx — skip in Phase 1 (no competitor data)

        # Rule 6: rounding (fail-safe)
        step = resolve_rounding_step(current_price, menu_role, rules)
        if "rounding" not in relaxed and candidate_price % step != 0:
            violations.append(f"rounding: {candidate_price} not divisible by {step}")

        # Rule 7: no_psychological
        r = rules.get("no_psychological")
        if ("no_psychological" not in relaxed
                and r is not None and r.get("enabled", True)
                and menu_role in PREMIUM_ROLES):
            endings = r.get("endings", [9, 99])
            last_digits = int(candidate_price) % 100
            if last_digits in endings:
                violations.append(f"no_psychological: ending {last_digits} on {menu_role}")

        # Rule 8: stop_list. params.block задаёт направление: 'any' (по
        # умолчанию — не трогать вовсе), 'increase' (не повышать, вернуть
        # можно) или 'decrease'. Направленная блокировка нужна как раз для
        # позиций с доказанным убытком от повышения: поднимать нельзя,
        # а откат к прежней цене — именно то, что требуется.
        r = rules.get("stop_list")
        if r is not None and candidate_price != current_price:
            block = str(r.get("block", "any")).lower()
            up = candidate_price > current_price
            if (block not in ("increase", "decrease")
                    or (block == "increase" and up)
                    or (block == "decrease" and not up)):
                violations.append(f"stop_list: {'increase' if up else 'decrease'} blocked ({block})")

        return (len(violations) == 0, violations)

    def list_rules(
        self,
        rule_type: Optional[str] = None,
        scope_type: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> list[dict]:
        conditions = ["1=1"]
        params: dict[str, Any] = {}
        if rule_type:
            conditions.append("rule_type = :rule_type")
            params["rule_type"] = rule_type
        if scope_type:
            conditions.append("scope_type = :scope_type")
            params["scope_type"] = scope_type
        if is_active is not None:
            conditions.append("is_active = :is_active")
            params["is_active"] = is_active

        rows = self.db.execute(
            text(f"""
                SELECT id, rule_type, scope_type, scope_id, params,
                       is_active, configured_by_role, effective_from, effective_to
                FROM pricing_rule
                WHERE {' AND '.join(conditions)}
                ORDER BY rule_type, scope_type
            """),
            params,
        ).fetchall()

        return [
            {
                "id": r[0], "rule_type": r[1], "scope_type": r[2],
                "scope_id": r[3], "params": r[4], "is_active": r[5],
                "configured_by_role": r[6], "effective_from": r[7],
                "effective_to": r[8],
            }
            for r in rows
        ]

    def create_rule(self, data: dict, actor: Optional[str] = None) -> dict:
        from .pricing_audit import log_audit

        if data["rule_type"] not in VALID_RULE_TYPES:
            raise ValueError(
                f"Invalid rule_type '{data['rule_type']}'. "
                f"Must be one of: {', '.join(sorted(VALID_RULE_TYPES))}"
            )
        if data["scope_type"] not in VALID_SCOPE_TYPES:
            raise ValueError(f"Invalid scope_type '{data['scope_type']}'")
        allowed_scopes = RULE_TYPE_SCOPES.get(data["rule_type"])
        if allowed_scopes and data["scope_type"] not in allowed_scopes:
            raise ValueError(
                f"rule_type '{data['rule_type']}' allows scopes: "
                f"{', '.join(sorted(allowed_scopes))}"
            )
        row = self.db.execute(
            text("""
                INSERT INTO pricing_rule
                    (rule_type, scope_type, scope_id, params, configured_by_role,
                     effective_from, effective_to)
                VALUES (:rule_type, :scope_type, :scope_id, CAST(:params AS jsonb),
                        :configured_by_role, COALESCE(:effective_from, CURRENT_DATE),
                        :effective_to)
                RETURNING id
            """),
            {
                "rule_type": data["rule_type"],
                "scope_type": data["scope_type"],
                "scope_id": data.get("scope_id"),
                "params": json.dumps(data["params"]),
                "configured_by_role": data.get("configured_by_role"),
                "effective_from": data.get("effective_from"),
                "effective_to": data.get("effective_to"),
            },
        ).fetchone()
        rule_id = row[0]
        log_audit(self.db, "rule", rule_id, "create", actor=actor,
                  details={"rule_type": data["rule_type"], "scope_type": data["scope_type"],
                           "scope_id": data.get("scope_id"), "params": data["params"]})
        self.db.commit()
        return {"status": "ok", "id": rule_id}

    def update_rule(self, rule_id: int, data: dict, actor: Optional[str] = None) -> dict:
        sets = ["updated_at = NOW()"]
        params: dict[str, Any] = {"id": rule_id}
        if "params" in data and data["params"] is not None:
            sets.append("params = CAST(:params AS jsonb)")
            params["params"] = json.dumps(data["params"])
        if "is_active" in data and data["is_active"] is not None:
            sets.append("is_active = :is_active")
            params["is_active"] = data["is_active"]
        if "effective_from" in data and data["effective_from"] is not None:
            sets.append("effective_from = :effective_from")
            params["effective_from"] = data["effective_from"]
        if "effective_to" in data and data["effective_to"] is not None:
            sets.append("effective_to = :effective_to")
            params["effective_to"] = data["effective_to"]

        result = self.db.execute(
            text(f"UPDATE pricing_rule SET {', '.join(sets)} WHERE id = :id"),
            params,
        )
        if result.rowcount == 0:
            self.db.rollback()
            return {"status": "error", "message": f"Rule {rule_id} not found"}
        from .pricing_audit import log_audit
        log_audit(self.db, "rule", rule_id, "update", actor=actor,
                  details={k: v for k, v in data.items() if v is not None})
        self.db.commit()
        return {"status": "ok"}

    def delete_rule(self, rule_id: int, actor: Optional[str] = None) -> dict:
        from .pricing_audit import log_audit

        # Hard delete: soft-deleted строки блокировали повторное создание
        # правила через UNIQUE (rule_type, scope_type, scope_id).
        result = self.db.execute(
            text("""
                DELETE FROM pricing_rule WHERE id = :id
                RETURNING rule_type, scope_type, scope_id, params
            """),
            {"id": rule_id},
        )
        deleted = result.fetchone()
        if deleted is None:
            self.db.rollback()
            return {"status": "error", "message": f"Rule {rule_id} not found"}
        log_audit(self.db, "rule", rule_id, "delete", actor=actor,
                  details={"rule_type": deleted[0], "scope_type": deleted[1],
                           "scope_id": deleted[2], "params": deleted[3]})
        self.db.commit()
        return {"status": "ok"}
