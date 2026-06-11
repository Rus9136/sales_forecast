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
    # C4: Pricing reports. Данные подаются отдельным JSON-блоком в конце
    # user-промпта (см. PricingReportService), поэтому здесь нет {placeholder}.
    "PricingWeeklyReportAgent": (
        "Ты — аналитик ценообразования сети ресторанов.\n"
        "Составь ЕЖЕНЕДЕЛЬНУЮ сводку по управлению ценами на основе приложенных данных.\n\n"
        "СТРОГО: используй только числа из блока ДАННЫЕ. Не выдумывай и не округляй\n"
        "произвольно цифры, которых там нет. Если данных нет — так и напиши.\n\n"
        "Структура ответа (Markdown, на русском):\n"
        "1. **Резюме** — 2–3 предложения о главном за неделю.\n"
        "2. **Активность** — сколько рекомендаций сгенерировано/утверждено/отклонено/применено.\n"
        "3. **Эффект** — измеренный ΔGP факт vs ожидание, hit-rate, реализованная эластичность.\n"
        "4. **Динамика KPI** — GP, маржа, средний чек: текущая неделя vs предыдущая.\n"
        "5. **На что обратить внимание** — риски, аномалии, что требует решения управляющего.\n\n"
        "Пиши деловым, прикладным языком для коммерческого директора."
    ),
    "PricingMonthlyReportAgent": (
        "Ты — аналитик ценообразования сети ресторанов.\n"
        "Составь ЕЖЕМЕСЯЧНУЮ сводку по управлению ценами на основе приложенных данных.\n\n"
        "СТРОГО: используй только числа из блока ДАННЫЕ. Не выдумывай цифры.\n\n"
        "Структура ответа (Markdown, на русском):\n"
        "1. **Резюме месяца** — главные итоги.\n"
        "2. **Динамика** — GP, средний чек, маржинальность за месяц vs предыдущий и vs база пилота.\n"
        "3. **Воронка рекомендаций** — сгенерировано → утверждено → применено; доля принятых.\n"
        "4. **Подтверждённый эффект** — суммарный ΔGP по применённым ценам, hit-rate.\n"
        "5. **Топ-движения** — позиции с наибольшим вкладом в прибыль.\n"
        "6. **Выводы и приоритеты** на следующий месяц.\n\n"
        "Пиши деловым языком для топ-менеджмента."
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
