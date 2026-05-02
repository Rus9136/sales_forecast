"""Static metadata for calculation models — drives the UI scheme editor.

Each entry describes:
  - Human name / description shown in the model dropdown.
  - Which config blocks the model expects (kpis, grades, revenue_source,
    components, etc.) — the UI uses these flags to show/hide editor sections.
  - The grade type ("flat" → tenge, "rate" → percent, "none" → no grades).
  - Which boolean options the model honours (so the UI knows which switches to render).
  - Typical positions the model is used for (informational only).

Keep this in sync with app/bonus/schemas/calc_configs/*.py — both files describe
the same shape from different angles (validation vs UI).
"""

from __future__ import annotations


CALCULATION_MODEL_METADATA: dict[str, dict] = {
    "flat_by_kpi": {
        "code": "flat_by_kpi",
        "name": "Фикс. сумма по KPI",
        "description": (
            "% выполнения KPI → грейд → фиксированная сумма в тенге. "
            "Используется для управляющего ресторана."
        ),
        "typical_positions": ["restaurant_director"],
        "requires_kpis": True,
        "requires_revenue_source": False,
        "requires_grades": True,
        "grade_type": "flat",        # колонки грейда: from%, to%, value (₸)
        "supports_components": False,
        "supports_shifts_proration": True,
        "options": [
            {"key": "apply_shifts_proration", "type": "bool", "default": False,
             "label": "Пропорционально сменам",
             "hint": "Бонус × (отработано / норма)"},
            {"key": "below_threshold_bonus", "type": "money", "default": "0",
             "label": "Бонус ниже порога (₸)",
             "hint": "Что начислить если KPI ниже минимального грейда (обычно 0)"},
        ],
    },
    "revenue_percent_by_kpi": {
        "code": "revenue_percent_by_kpi",
        "name": "% от выручки × KPI",
        "description": (
            "% KPI → грейд (как ставка) → выручка × ставка. "
            "Используется для менеджера и официанта."
        ),
        "typical_positions": ["manager_admin", "waiter"],
        "requires_kpis": True,
        "requires_revenue_source": True,
        "requires_grades": True,
        "grade_type": "rate",        # колонки грейда: from%, to%, rate (%)
        "supports_components": False,
        "supports_shifts_proration": True,
        "options": [
            {"key": "apply_shifts_proration", "type": "bool", "default": False,
             "label": "Пропорционально сменам",
             "hint": "Бонус × (отработано / норма)"},
            {"key": "only_worked_days", "type": "bool", "default": False,
             "label": "Только отработанные дни",
             "hint": "Учитывать выручку только за дни с фактической сменой"},
        ],
    },
    "revenue_direct": {
        "code": "revenue_direct",
        "name": "Прямой % от выручки",
        "description": (
            "Выручка × фиксированный процент, без KPI и грейдов. "
            "Используется для кассира и старшего бариста."
        ),
        "typical_positions": ["cashier", "senior_barista"],
        "requires_kpis": False,
        "requires_revenue_source": True,
        "requires_grades": False,
        "requires_rate": True,       # одна фиксированная ставка
        "grade_type": "none",
        "supports_components": False,
        "supports_shifts_proration": True,
        "options": [
            {"key": "apply_shifts_proration", "type": "bool", "default": False,
             "label": "Пропорционально сменам",
             "hint": "Бонус × (отработано / норма)"},
            {"key": "shifts_proration_formula", "type": "enum", "default": "ratio",
             "label": "Формула пропорции",
             "options": [
                 {"value": "ratio",
                  "label": "ratio: выручка × ставка × (отработано / норма)"},
                 {"value": "norm_then_actual",
                  "label": "norm_then_actual: (выручка / норма) × отработано × ставка"},
             ],
             "hint": "Математически результаты совпадают, разные формулировки для документации"},
        ],
    },
    "combined_products": {
        "code": "combined_products",
        "name": "Комбинированный (продукты)",
        "description": (
            "Несколько компонентов выручки (готовая, приготовленная и т.д.), "
            "у каждого свой процент. Бонус = Σ(выручка × ставка). "
            "Используется для бариста."
        ),
        "typical_positions": ["barista"],
        "requires_kpis": False,
        "requires_revenue_source": False,
        "requires_grades": False,
        "grade_type": "none",
        "supports_components": True,
        "supports_shifts_proration": True,
        "options": [
            {"key": "apply_shifts_proration", "type": "bool", "default": False,
             "label": "Пропорционально сменам",
             "hint": "Итог × (отработано / норма)"},
            {"key": "require_no_violations", "type": "bool", "default": False,
             "label": "Требовать отсутствие нарушений",
             "hint": "Если у сотрудника есть нарушения за период — бонус 0"},
        ],
    },
    "team_revenue_by_kpi": {
        "code": "team_revenue_by_kpi",
        "name": "Командный (KITCHEN)",
        "description": (
            "KPI команды → гейт (если ниже минимума, всем 0). "
            "Распределение через веса слотов: бонус = выручка × вес слота × (отработано / норма). "
            "Используется для KITCHEN-команд."
        ),
        "typical_positions": ["kitchen_team"],
        "requires_kpis": True,        # KPI работают как gate
        "requires_revenue_source": True,
        "requires_grades": True,      # грейды используются только как порог
        "grade_type": "rate",
        "supports_components": False,
        "supports_shifts_proration": True,
        "is_team_model": True,        # требует team_id вместо position_id
        "options": [
            {"key": "below_threshold_bonus_zero", "type": "bool", "default": True,
             "label": "Гейт по минимальному грейду",
             "hint": "Если общий KPI ниже минимального грейда — всей команде 0"},
            {"key": "distribution_formula", "type": "enum",
             "default": "revenue * slot_weight * shifts_ratio",
             "label": "Формула распределения",
             "options": [
                 {"value": "revenue * slot_weight * shifts_ratio",
                  "label": "revenue × slot_weight × shifts_ratio (текущая)"},
                 {"value": "revenue * grade_rate * slot_share * shifts_ratio",
                  "label": "revenue × grade_rate × slot_share × shifts_ratio"},
             ],
             "hint": "Как распределить общий бонус по слотам команды"},
            {"key": "apply_shifts_proration", "type": "bool", "default": True,
             "label": "Пропорционально сменам",
             "hint": "Учитывать (отработано / норма) для каждого члена команды"},
            {"key": "exclude_probation_period", "type": "bool", "default": True,
             "label": "Исключить испытательный срок",
             "hint": "Сотрудники на испытательном сроке получают 0"},
            {"key": "exclude_violators", "type": "bool", "default": False,
             "label": "Исключить нарушителей",
             "hint": "Сотрудники с флагом нарушения получают 0"},
        ],
    },
}
