"""Default prompt templates and DB-backed prompt management.

Each agent has a hardcoded fallback prompt. When `ai_prompts` table contains
a row for a given agent, that row wins. Updates from the UI are persisted
back to the table.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from ...models.ai import AIPrompt


DEFAULT_PROMPTS: dict[str, str] = {
    "SalesAnalysisAgent": (
        "Ты — AI-аналитик продаж.\n"
        "Проанализируй прогноз продаж по дням, сравнение план-факт, и почасовые продажи:\n\n"
        "— Прогноз: {forecast}\n"
        "— План/факт: {plan_vs_fact}\n"
        "— Почасовые: {hourly_sales}\n\n"
        "Сделай выводы о динамике выручки, выяви пики и провалы, "
        "укажи на аномалии и сильные/слабые дни."
    ),
    "OptimizationAgent": (
        "Ты — AI-консультант по оптимизации.\n"
        "Используй выводы других аналитиков по продажам, ФОТ, расписанию и отзывам клиентов.\n\n"
        "{agent_results}\n\n"
        "Дай список конкретных шагов по оптимизации работы ресторана: "
        "как повысить выручку, сократить расходы и улучшить сервис."
    ),
    "NarrativeAgent": (
        "Ты — бизнес-консультант для управляющего рестораном.\n"
        "Составь итоговый отчёт и резюме на основе аналитики по продажам, персоналу, отзывам и рекомендациям.\n\n"
        "Информация о подразделении: {department_info}\n\n"
        "Результаты других агентов:\n{agent_results}\n\n"
        "В начале — краткое резюме, затем подробности по разделам: "
        "продажи, персонал, отзывы, шаги по улучшению."
    ),
    # Disabled in Variant A but kept for forward compatibility.
    "PayrollAnalysisAgent": (
        "Ты — AI-аналитик затрат.\n"
        "Анализируй выплаты сотрудникам и график смен за период.\n"
        "Сравни расходы на персонал с прогнозом продаж, оцени эффективность.\n\n"
        "— ФОТ и смены: {payroll}\n"
        "— Прогноз продаж: {forecast}"
    ),
    "StaffingAgent": (
        "Ты — AI по оптимизации смен.\n"
        "Оцени, достаточно ли персонала на пиковых часах продаж.\n\n"
        "— Смены: {payroll}\n"
        "— Почасовые продажи: {hourly_sales}\n\n"
        "Дай советы по оптимальному распределению сотрудников."
    ),
    "ReputationAgent": (
        "Ты — AI-аналитик клиентской репутации.\n\n"
        "- Последние отзывы клиентов: {reviews}\n\n"
        "1. Проанализируй основные темы и настроения отзывов.\n"
        "2. Найди часто повторяющиеся жалобы.\n"
        "3. Отметь, что больше всего нравится клиентам.\n"
        "4. Дай советы по улучшению сервиса.\n\n"
        "Сделай выводы краткими и прикладными для управляющего."
    ),
}


def get_prompt(db: Session, agent_name: str) -> str:
    """Fetch the active prompt template — DB row wins over default."""
    row = db.query(AIPrompt).filter(AIPrompt.agent_name == agent_name).first()
    if row and row.prompt_text:
        return row.prompt_text
    default = DEFAULT_PROMPTS.get(agent_name)
    if default is None:
        raise KeyError(f"No prompt registered for agent '{agent_name}'")
    return default


def upsert_prompt(db: Session, agent_name: str, prompt_text: str) -> None:
    row = db.query(AIPrompt).filter(AIPrompt.agent_name == agent_name).first()
    if row:
        row.prompt_text = prompt_text
        row.updated_at = datetime.utcnow()
    else:
        row = AIPrompt(agent_name=agent_name, prompt_text=prompt_text)
        db.add(row)
    db.commit()


def list_all_prompts(db: Session) -> dict[str, dict]:
    """Return a map of agent_name -> {prompt, source, updated_at}.

    `source` is "db" if a row exists in ai_prompts, otherwise "default".
    Includes all known agents (defaults + DB rows).
    """
    db_rows = {row.agent_name: row for row in db.query(AIPrompt).all()}
    out: dict[str, dict] = {}
    for agent_name, default_text in DEFAULT_PROMPTS.items():
        row = db_rows.get(agent_name)
        if row:
            out[agent_name] = {
                "prompt": row.prompt_text,
                "source": "db",
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
        else:
            out[agent_name] = {
                "prompt": default_text,
                "source": "default",
                "updated_at": None,
            }
    # Surface DB-only prompts that aren't in defaults
    for agent_name, row in db_rows.items():
        if agent_name not in out:
            out[agent_name] = {
                "prompt": row.prompt_text,
                "source": "db",
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
    return out
