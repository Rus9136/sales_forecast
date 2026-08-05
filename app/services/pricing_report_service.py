"""C4: сбор данных и LLM-генерация еженедельных/ежемесячных отчётов по ценам.

Собирает метрики ценообразования за период прямыми SQL (как остальные
pricing-сервисы), затем зовёт Claude-движок существующей AI-подсистемы для
нарратива. Данные подаются модели отдельным JSON-блоком — числа не выдумываются.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..models.pricing_analytics import PricingReport

logger = logging.getLogger(__name__)


def _f(v) -> Optional[float]:
    return float(v) if v is not None else None


def previous_period(report_type: str, start: date, end: date) -> tuple[date, date]:
    """Период той же длины непосредственно перед текущим."""
    if report_type == "monthly":
        prev_end = start - timedelta(days=1)
        prev_start = prev_end.replace(day=1)
        return prev_start, prev_end
    length = (end - start).days + 1
    return start - timedelta(days=length), start - timedelta(days=1)


class PricingReportService:
    def __init__(self, db: Session):
        self.db = db

    # ── Data collection ────────────────────────────────────────────
    def _dept_clause(self, department_id: Optional[str], col: str = "department_id") -> str:
        return f" AND {col} = CAST(:dept AS uuid)" if department_id else ""

    def _recommendation_activity(self, start: date, end: date, dept: Optional[str]) -> dict:
        rows = self.db.execute(
            text(f"""
                SELECT status, COUNT(*) AS n
                FROM price_recommendation
                WHERE created_at::date BETWEEN :start AND :end
                {self._dept_clause(dept)}
                GROUP BY status
            """),
            {"start": start, "end": end, "dept": dept},
        ).mappings().all()
        return {r["status"]: r["n"] for r in rows}

    def _outcomes(self, start: date, end: date, dept: Optional[str]) -> dict:
        # фильтр по created_at (дате появления оценки), не по applied_at:
        # outcome появляется через 14+ дней после применения, поэтому фильтр
        # по applied_at за отчётную неделю всегда давал evaluated=0
        r = self.db.execute(
            text(f"""
                SELECT COUNT(*) AS n,
                       COALESCE(SUM(expected_delta_gp), 0) AS exp_gp,
                       COALESCE(SUM(actual_delta_gp), 0) AS act_gp,
                       COALESCE(SUM(incremental_delta_gp), 0) AS inc_gp,
                       COUNT(*) FILTER (WHERE incremental_delta_gp > 0) AS positive,
                       -- «подтверждено» = интервал не накрывает ноль
                       COUNT(*) FILTER (WHERE effect_ci_low > 0 OR effect_ci_high < 0) AS significant,
                       COALESCE(SUM(incremental_delta_gp)
                                FILTER (WHERE effect_ci_low > 0 OR effect_ci_high < 0), 0) AS sig_gp,
                       COUNT(*) FILTER (WHERE measurable IS NOT TRUE) AS not_measurable,
                       AVG(realized_elasticity) AS avg_eps
                FROM price_recommendation_outcome
                WHERE created_at::date BETWEEN :start AND :end
                {self._dept_clause(dept)}
            """),
            {"start": start, "end": end, "dept": dept},
        ).mappings().first()
        n = r["n"] or 0
        return {
            "evaluated": n,
            "expected_delta_gp": _f(r["exp_gp"]),
            # эффект решения о цене, очищенный от фона категории — основная цифра
            "incremental_delta_gp": _f(r["inc_gp"]),
            # изменение по кассе (фон не вычтен), приведено к равному числу дней
            "actual_delta_gp": _f(r["act_gp"]),
            "positive": r["positive"] or 0,
            "hit_rate": round(r["positive"] / n, 4) if n else None,
            # сколько результатов отличимо от шума и сколько денег за ними стоит
            "significant": r["significant"] or 0,
            "significant_delta_gp": _f(r["sig_gp"]),
            # позиции без контрольной группы: эффект не оценивался вовсе
            "not_measurable": r["not_measurable"] or 0,
            "avg_realized_elasticity": _f(r["avg_eps"]),
        }

    def _kpi(self, start: date, end: date, dept: Optional[str]) -> dict:
        r = self.db.execute(
            text(f"""
                SELECT COALESCE(SUM(total_revenue), 0) AS revenue,
                       COALESCE(SUM(gross_profit), 0) AS gp,
                       COALESCE(SUM(total_cost), 0) AS cost,
                       COALESCE(SUM(total_receipts), 0) AS receipts
                FROM department_weekly_summary
                WHERE week_start BETWEEN :start AND :end
                {self._dept_clause(dept)}
            """),
            {"start": start, "end": end, "dept": dept},
        ).mappings().first()
        revenue = _f(r["revenue"]) or 0.0
        gp = _f(r["gp"]) or 0.0
        receipts = r["receipts"] or 0
        return {
            "revenue": revenue,
            "gross_profit": gp,
            "gp_margin": round(gp / revenue, 4) if revenue else None,
            "receipts": receipts,
            "avg_receipt_sum": round(revenue / receipts, 2) if receipts else None,
        }

    def _top_movers(self, start: date, end: date, dept: Optional[str]) -> list[dict]:
        rows = self.db.execute(
            text(f"""
                SELECT pr.product_id, p.name AS product_name,
                       pr.current_price, pr.recommended_price, pr.delta_pct, pr.delta_gp, pr.status
                FROM price_recommendation pr
                JOIN product p ON p.id = pr.product_id
                WHERE pr.created_at::date BETWEEN :start AND :end
                  AND pr.status IN ('approved', 'applied')
                {self._dept_clause(dept, 'pr.department_id')}
                ORDER BY pr.delta_gp DESC NULLS LAST
                LIMIT 8
            """),
            {"start": start, "end": end, "dept": dept},
        ).mappings().all()
        return [
            {
                "product_name": r["product_name"],
                "current_price": _f(r["current_price"]),
                "recommended_price": _f(r["recommended_price"]),
                "delta_pct": _f(r["delta_pct"]),
                "delta_gp": _f(r["delta_gp"]),
                "status": r["status"],
            }
            for r in rows
        ]

    def _baseline(self, dept: Optional[str]) -> Optional[dict]:
        scope = "department" if dept else "network"
        r = self.db.execute(
            text(f"""
                SELECT label, weekly_gp_avg, weekly_gp_stddev, gp_margin,
                       avg_receipt_sum, active_skus, baseline_from, baseline_to
                FROM pricing_baseline_kpi
                WHERE scope = :scope {self._dept_clause(dept)}
                ORDER BY created_at DESC
                LIMIT 1
            """),
            {"scope": scope, "dept": dept},
        ).mappings().first()
        if not r:
            return None
        return {
            "label": r["label"],
            "weekly_gp_avg": _f(r["weekly_gp_avg"]),
            "weekly_gp_stddev": _f(r["weekly_gp_stddev"]),
            "gp_margin": _f(r["gp_margin"]),
            "avg_receipt_sum": _f(r["avg_receipt_sum"]),
            "active_skus": r["active_skus"],
            "from": str(r["baseline_from"]),
            "to": str(r["baseline_to"]),
        }

    def collect_data(
        self, report_type: str, start: date, end: date, dept: Optional[str] = None
    ) -> dict[str, Any]:
        prev_start, prev_end = previous_period(report_type, start, end)
        return {
            "report_type": report_type,
            "scope": "department" if dept else "network",
            "period": {"start": str(start), "end": str(end)},
            "prev_period": {"start": str(prev_start), "end": str(prev_end)},
            "recommendations": self._recommendation_activity(start, end, dept),
            "outcomes": self._outcomes(start, end, dept),
            "kpi_current": self._kpi(start, end, dept),
            "kpi_previous": self._kpi(prev_start, prev_end, dept),
            "baseline": self._baseline(dept),
            "top_movers": self._top_movers(start, end, dept),
        }

    # ── Headline KPIs (для карточек UI без парсинга нарратива) ──────
    @staticmethod
    def _headline(data: dict) -> dict:
        cur = data["kpi_current"]
        prev = data["kpi_previous"]
        out = data["outcomes"]
        gp_delta_pct = None
        if prev.get("gross_profit"):
            gp_delta_pct = round((cur["gross_profit"] - prev["gross_profit"]) / prev["gross_profit"] * 100, 2)
        rec = data["recommendations"]
        return {
            "gross_profit": cur.get("gross_profit"),
            "gp_delta_pct": gp_delta_pct,
            "gp_margin": cur.get("gp_margin"),
            "avg_receipt_sum": cur.get("avg_receipt_sum"),
            "recs_approved": rec.get("approved", 0),
            "recs_applied": rec.get("applied", 0),
            "outcomes_evaluated": out.get("evaluated", 0),
            # эффект решений о цене — очищенный от фона; кассовую дельту
            # оставляем рядом, чтобы в отчёте не подменялись понятия
            "incremental_delta_gp": out.get("incremental_delta_gp"),
            "actual_delta_gp": out.get("actual_delta_gp"),
            "outcomes_significant": out.get("significant", 0),
            "significant_delta_gp": out.get("significant_delta_gp"),
            "outcomes_not_measurable": out.get("not_measurable", 0),
            "hit_rate": out.get("hit_rate"),
        }

    # ── LLM narrative ──────────────────────────────────────────────
    async def _narrate(self, report_type: str, data: dict, provider: str) -> tuple[Optional[str], Optional[str], str]:
        from .ai.engines.dispatcher import get_dispatcher
        from .ai.prompts import get_prompt

        agent_name = "PricingWeeklyReportAgent" if report_type == "weekly" else "PricingMonthlyReportAgent"
        engine = get_dispatcher().get_engine(provider)
        if engine is None or not engine.is_configured():
            return None, None, "no_llm"

        template = get_prompt(self.db, agent_name)
        user_prompt = (
            template
            + "\n\nДАННЫЕ (JSON):\n"
            + json.dumps(data, ensure_ascii=False, default=str)
        )
        system_prompt = "Ты — аналитик ценообразования сети ресторанов. Отвечай на русском, строго по приложенным данным."
        # db=None → движок не пишет в ai_prompt_logs (FK на ai_recommendations);
        # сам отчёт хранит нарратив и статус.
        result = await engine.analyze_with_agent(
            agent_name=agent_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            db=None,
            max_tokens=2000,
            temperature=0.4,
        )
        model = getattr(engine, "model", None)
        if result.success:
            return result.content, model, "ok"
        logger.error("Pricing report narrative failed: %s", result.error)
        return None, model, "error"

    async def generate(
        self,
        report_type: str,
        start: date,
        end: date,
        dept: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> PricingReport:
        from .ai.engines.dispatcher import get_dispatcher

        provider = (provider or get_dispatcher().DEFAULT_PROVIDER).lower()
        data = self.collect_data(report_type, start, end, dept)
        kpis = self._headline(data)
        narrative, model, status = await self._narrate(report_type, data, provider)

        report = PricingReport(
            report_type=report_type,
            scope="department" if dept else "network",
            department_id=dept,
            period_start=start,
            period_end=end,
            data=data,
            kpis=kpis,
            narrative=narrative,
            provider=provider,
            model=model,
            status=status,
        )
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)
        return report


def last_full_week(today: date) -> tuple[date, date]:
    """Понедельник–воскресенье предыдущей завершённой ISO-недели."""
    # today.weekday(): Mon=0; this week's Monday:
    this_monday = today - timedelta(days=today.weekday())
    start = this_monday - timedelta(days=7)
    end = this_monday - timedelta(days=1)
    return start, end


def last_full_month(today: date) -> tuple[date, date]:
    """Первое–последнее число предыдущего календарного месяца."""
    first_this = today.replace(day=1)
    end = first_this - timedelta(days=1)
    start = end.replace(day=1)
    return start, end
