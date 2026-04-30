"""Multi-agent analysis orchestrator.

Variant A: only 3 agents are enabled — SalesAnalysisAgent, OptimizationAgent,
NarrativeAgent. Phase 1 produces base analyses (Sales). Phase 2 synthesises
those into recommendations (Optimization → Narrative).

Disabled agents (Payroll/Staffing/Reputation) remain in the registry so they
can be turned on later by setting `enabled=True` once the data sources exist.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from .data_collector import collect_dashboard_data
from .engines import AgentResult, get_dispatcher
from .prompts import get_prompt

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    name: str
    description: str
    data_fields: list[str]
    enabled: bool = True
    pause_after_seconds: int = 5  # Variant A uses local data so we can be aggressive


# Variant A registry. Only 3 agents enabled.
AGENTS: dict[str, AgentConfig] = {
    "SalesAnalysisAgent": AgentConfig(
        name="SalesAnalysisAgent",
        description="AI-аналитик продаж",
        data_fields=["forecast", "plan_vs_fact", "hourly_sales"],
        enabled=True,
        pause_after_seconds=5,
    ),
    "PayrollAnalysisAgent": AgentConfig(
        name="PayrollAnalysisAgent",
        description="AI-аналитик затрат (ФОТ)",
        data_fields=["payroll", "forecast"],
        enabled=False,
    ),
    "StaffingAgent": AgentConfig(
        name="StaffingAgent",
        description="AI по оптимизации смен",
        data_fields=["payroll", "hourly_sales"],
        enabled=False,
    ),
    "ReputationAgent": AgentConfig(
        name="ReputationAgent",
        description="AI-аналитик клиентской репутации",
        data_fields=["reviews"],
        enabled=False,
    ),
    "OptimizationAgent": AgentConfig(
        name="OptimizationAgent",
        description="AI-консультант по оптимизации",
        data_fields=["agent_results"],
        enabled=True,
        pause_after_seconds=10,
    ),
    "NarrativeAgent": AgentConfig(
        name="NarrativeAgent",
        description="Бизнес-консультант для управляющего",
        data_fields=["agent_results", "department_info"],
        enabled=True,
        pause_after_seconds=0,
    ),
}


SYSTEM_PROMPT_TEMPLATE = (
    "Ты — AI-аналитик ресторанного бизнеса. Твоя роль: {role}. "
    "Анализируй предоставленные данные профессионально и дай конкретные рекомендации. "
    "Отвечай на русском языке, структурированно и по делу."
)


def _day_info(date_str: str) -> dict:
    """Day-of-week info using Asia/Almaty (UTC+5)."""
    try:
        # Treat the date as midday Almaty (UTC+5) to avoid TZ edge cases.
        dt = datetime.fromisoformat(date_str)
    except Exception:
        return {"day": "unknown", "is_weekend": False}
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    weekday = dt.weekday()  # Mon=0..Sun=6
    return {
        "day": days[weekday],
        "is_weekend": weekday >= 5,
    }


def compress_data_for_tokens(data: dict[str, Any]) -> dict[str, Any]:
    """Reduce raw input dict to a compact form to save tokens.

    Mirrors hr-miniapp's compressDataForTokens but adapted to the schema
    produced by data_collector.
    """
    compressed: dict[str, Any] = {}

    plan_vs_fact = data.get("plan_vs_fact") or []
    actual_map = {
        item["date"]: item.get("actual_sales")
        for item in plan_vs_fact
        if item.get("date") and item.get("actual_sales") is not None
    }

    forecast = data.get("forecast") or []
    if forecast:
        compressed["forecast"] = []
        for item in forecast[:10]:
            actual = item.get("actual_sales")
            if actual is None:
                actual = actual_map.get(item.get("date"))
            compressed["forecast"].append(
                {
                    "date": item.get("date"),
                    "plan": _kfmt(item.get("predicted_sales")),
                    "fact": _kfmt(actual),
                }
            )

    if plan_vs_fact:
        compressed["plan_vs_fact"] = [
            {
                "date": item.get("date"),
                "plan": _kfmt(item.get("predicted_sales")),
                "fact": _kfmt(item.get("actual_sales")),
                "deviation": item.get("error_percentage") or 0,
            }
            for item in plan_vs_fact[:10]
        ]

    hourly = data.get("hourly_sales") or []
    if hourly:
        items = sorted(hourly, key=lambda x: (x.get("date") or "", x.get("hour") or 0))
        # Cap to ~7 days of hourly data to keep prompts within token budgets.
        items = items[-7 * 24 :]
        compressed["hourly_sales"] = []
        for item in items:
            info = _day_info(item.get("date") or "")
            compressed["hourly_sales"].append(
                {
                    "date": item.get("date"),
                    "day": info["day"],
                    "h": item.get("hour"),
                    "type": "weekend" if info["is_weekend"] else "weekday",
                    "sales": _kfmt(item.get("sales_amount")),
                }
            )

    payroll = data.get("payroll")
    if payroll:
        compressed["payroll"] = [
            {
                "name": (item.get("employee_name") or "").split(" ")[0] or "N/A",
                "shifts": item.get("shifts") or [],
                "payroll": _kfmt(item.get("payroll_total") or item.get("total_payroll")),
            }
            for item in payroll[:20]
        ]

    reviews = data.get("reviews")
    if reviews:
        compressed["reviews"] = [
            {
                "rating": item.get("rating") or 0,
                "text": (item.get("text") or item.get("comment") or "")[:300],
            }
            for item in reviews
        ]

    dept = data.get("department_info")
    if dept:
        compressed["department_info"] = {
            "name": dept.get("object_name") or "N/A",
            "company": dept.get("object_company") or "N/A",
            "city": dept.get("city"),
            "brand": dept.get("brand"),
            "segment": dept.get("segment_type"),
            "is_24_7": dept.get("is_24_7"),
            "opening_hour": dept.get("opening_hour"),
            "closing_hour": dept.get("closing_hour"),
            "hall_area": dept.get("hall_area"),
            "kitchen_area": dept.get("kitchen_area"),
            "seats_count": dept.get("seats_count"),
        }

    if "agent_results" in data:
        compressed["agent_results"] = {
            name: (text[:500] + "...") if isinstance(text, str) and len(text) > 500 else text
            for name, text in data["agent_results"].items()
        }

    return compressed


def _kfmt(value: Optional[float]) -> str:
    """Format a number as 'NNNk' (rounded thousands)."""
    if value is None:
        return "N/A"
    try:
        return f"{round(float(value) / 1000)}k"
    except Exception:
        return "N/A"


def render_prompt(
    template: str,
    *,
    compressed: dict[str, Any],
    agent_results: Optional[dict[str, str]] = None,
) -> str:
    """Substitute {placeholder} fields in the prompt template.

    Missing fields render as a short note so the prompt stays readable.
    """
    placeholders = {
        "forecast": _stringify(compressed.get("forecast")),
        "plan_vs_fact": _stringify(compressed.get("plan_vs_fact")),
        "hourly_sales": _stringify(compressed.get("hourly_sales")),
        "payroll": _stringify(compressed.get("payroll")) or "(данные недоступны)",
        "reviews": _stringify(compressed.get("reviews")) or "(данные недоступны)",
        "department_info": _stringify(compressed.get("department_info")),
        "agent_results": _format_agent_results(agent_results),
    }

    result = template
    for key, value in placeholders.items():
        result = result.replace("{" + key + "}", value)
    return result


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2)


def _format_agent_results(results: Optional[dict[str, str]]) -> str:
    if not results:
        return ""
    lines = []
    for name, text in results.items():
        lines.append(f"--- {name} ---\n{text}\n")
    return "\n".join(lines)


@dataclass
class AnalysisOutcome:
    success: bool
    results: dict[str, str]
    errors: dict[str, str]
    skipped: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class MultiAgentSystem:
    """Orchestrates per-provider sequential agent runs."""

    def __init__(self) -> None:
        self.dispatcher = get_dispatcher()

    def list_enabled_agents(self) -> list[str]:
        return [name for name, cfg in AGENTS.items() if cfg.enabled]

    async def run_analysis(
        self,
        db: Session,
        *,
        analysis_id: int,
        raw_data: dict[str, Any],
        provider: str = "claude",
    ) -> AnalysisOutcome:
        engine = self.dispatcher.get_engine(provider)
        if not engine.is_configured():
            return AnalysisOutcome(
                success=False,
                results={},
                errors={"_engine": f"Provider '{provider}' is not configured"},
            )

        compressed = compress_data_for_tokens(raw_data)
        size_in = len(json.dumps(raw_data, default=str))
        size_out = len(json.dumps(compressed, default=str))
        logger.info(
            "MultiAgent: compressed %d -> %d chars (analysis_id=%d)",
            size_in,
            size_out,
            analysis_id,
        )

        results: dict[str, str] = {}
        errors: dict[str, str] = {}
        skipped: list[str] = []

        # Phase 1: base agents (those that depend only on raw data)
        phase1 = [
            "SalesAnalysisAgent",
            "PayrollAnalysisAgent",
            "StaffingAgent",
            "ReputationAgent",
        ]
        for agent_name in phase1:
            cfg = AGENTS.get(agent_name)
            if not cfg or not cfg.enabled:
                skipped.append(agent_name)
                continue
            if not self._has_required_data(cfg, compressed):
                skipped.append(agent_name)
                continue
            outcome = await self._run_agent(
                db,
                engine=engine,
                cfg=cfg,
                compressed=compressed,
                agent_results=None,
                analysis_id=analysis_id,
            )
            if outcome.success and outcome.content:
                results[agent_name] = outcome.content
            else:
                errors[agent_name] = outcome.error or "unknown error"
            if cfg.pause_after_seconds:
                await asyncio.sleep(cfg.pause_after_seconds)

        # Phase 2: synthesis agents (consume results from Phase 1)
        phase2 = ["OptimizationAgent", "NarrativeAgent"]
        for agent_name in phase2:
            cfg = AGENTS.get(agent_name)
            if not cfg or not cfg.enabled:
                skipped.append(agent_name)
                continue
            if not results:
                # Nothing to synthesize from
                errors[agent_name] = "No upstream agent results to synthesize"
                continue
            outcome = await self._run_agent(
                db,
                engine=engine,
                cfg=cfg,
                compressed=compressed,
                agent_results=results,
                analysis_id=analysis_id,
            )
            if outcome.success and outcome.content:
                results[agent_name] = outcome.content
            else:
                errors[agent_name] = outcome.error or "unknown error"
            if cfg.pause_after_seconds:
                await asyncio.sleep(cfg.pause_after_seconds)

        return AnalysisOutcome(
            success=bool(results),
            results=results,
            errors=errors,
            skipped=skipped,
            metadata={
                "provider": provider,
                "compressed_input_chars": size_out,
                "agents_total": len([c for c in AGENTS.values() if c.enabled]),
            },
        )

    async def run_single_agent(
        self,
        db: Session,
        *,
        analysis_id: int,
        agent_name: str,
        raw_data: dict[str, Any],
        previous_results: Optional[dict[str, str]] = None,
        prompt_override: Optional[str] = None,
        provider: str = "claude",
    ) -> AgentResult:
        cfg = AGENTS.get(agent_name)
        if not cfg:
            return AgentResult(
                success=False,
                agent_name=agent_name,
                provider=provider,
                error=f"Unknown agent '{agent_name}'",
            )

        engine = self.dispatcher.get_engine(provider)
        if not engine.is_configured():
            return AgentResult(
                success=False,
                agent_name=agent_name,
                provider=provider,
                error=f"Provider '{provider}' is not configured",
            )

        compressed = compress_data_for_tokens(raw_data)
        return await self._run_agent(
            db,
            engine=engine,
            cfg=cfg,
            compressed=compressed,
            agent_results=previous_results,
            analysis_id=analysis_id,
            prompt_override=prompt_override,
        )

    async def _run_agent(
        self,
        db: Session,
        *,
        engine,
        cfg: AgentConfig,
        compressed: dict[str, Any],
        agent_results: Optional[dict[str, str]],
        analysis_id: int,
        prompt_override: Optional[str] = None,
    ) -> AgentResult:
        template = prompt_override or get_prompt(db, cfg.name)
        user_prompt = render_prompt(
            template,
            compressed=compressed,
            agent_results=agent_results,
        )
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(role=cfg.description)
        return await engine.analyze_with_agent(
            agent_name=cfg.name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            analysis_id=analysis_id,
            db=db,
        )

    @staticmethod
    def _has_required_data(cfg: AgentConfig, compressed: dict[str, Any]) -> bool:
        for field_name in cfg.data_fields:
            if field_name == "agent_results":
                continue  # Phase 2 agents
            if field_name == "department_info":
                continue
            if not compressed.get(field_name):
                return False
        return True


_singleton: Optional[MultiAgentSystem] = None


def get_multi_agent_system() -> MultiAgentSystem:
    global _singleton
    if _singleton is None:
        _singleton = MultiAgentSystem()
    return _singleton


__all__ = [
    "AGENTS",
    "AnalysisOutcome",
    "MultiAgentSystem",
    "compress_data_for_tokens",
    "get_multi_agent_system",
    "render_prompt",
]
