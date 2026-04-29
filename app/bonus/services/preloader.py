"""CalculationPreloader — fetches everything needed by the calculator into a context.

Reads the scheme.config to learn which KPI/revenue sources are needed, calls
each source via DataSourceRegistry, and assembles a CalculationContext.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..calculator.context import CalculationContext, KpiFact, ShiftStats
from ..calculator.kpi_engine import score_kpi
from ..data_sources.base import DataSourceParams
from ..data_sources.registry import DataSourceRegistry
from ..models.assignment import BonusEmployeeAssignment
from ..models.monthly_plan import BonusMonthlyPlan
from ..models.team import BonusTeamPosition
from ..utils.decimal_utils import to_decimal
from ..utils.period import PeriodKey

logger = logging.getLogger(__name__)


class CalculationPreloader:
    def __init__(self, db: Session):
        self.db = db

    def preload(
        self,
        scheme_config: dict[str, Any],
        period: PeriodKey,
        department_id: str,
        department_name: str = "",
        employee_id: Optional[str] = None,
        employee_name: Optional[str] = None,
        team_id: Optional[int] = None,
        team_position_slot: Optional[str] = None,
        employment_type: str = "permanent",
        probation_until=None,
    ) -> CalculationContext:
        params_base = DataSourceParams(
            period=period,
            department_id=department_id,
            employee_id=employee_id,
        )

        # 1. Resolve target metrics from monthly_plan (so KPI configs can reference them)
        monthly_plans = self._load_monthly_plans(department_id, period)

        # 2. Fetch each KPI value
        kpi_values: dict[str, KpiFact] = {}
        for kpi_cfg in scheme_config.get("kpis", []):
            code = kpi_cfg["code"]
            source = kpi_cfg["source"]
            direction = kpi_cfg["direction"]
            target = self._resolve_target(kpi_cfg, monthly_plans)
            cap = kpi_cfg.get("cap_at_100", True)

            try:
                fact_raw = DataSourceRegistry.get(source).fetch(self.db, params_base)
                fact = to_decimal(fact_raw)
            except ValueError:
                logger.warning("Unknown KPI source: %s (kpi=%s)", source, code)
                fact = Decimal(0)

            percent = score_kpi(fact, target if target is not None else 0, direction, cap_at_100=cap)
            kpi_values[code] = KpiFact(
                code=code,
                fact=fact,
                target=target,
                percent=percent,
                direction=direction,
                weight=to_decimal(kpi_cfg.get("weight", 1)),
            )

        # 3. Fetch each revenue source
        revenue_values: dict[str, Decimal] = {}
        for rev_source in self._collect_revenue_sources(scheme_config):
            try:
                value = DataSourceRegistry.get(rev_source).fetch(self.db, params_base)
                revenue_values[rev_source] = to_decimal(value)
            except ValueError:
                logger.warning("Unknown revenue source: %s", rev_source)
                revenue_values[rev_source] = Decimal(0)

        # 4. Shifts
        try:
            shifts = DataSourceRegistry.get("tco_shifts").fetch(self.db, params_base)
        except ValueError:
            shifts = ShiftStats(worked=Decimal(0), norm=Decimal(22))

        # 5. Team slot weight
        team_position_weight = None
        if team_id and team_position_slot:
            row = (
                self.db.query(BonusTeamPosition.distribution_weight)
                .filter(
                    BonusTeamPosition.team_id == team_id,
                    BonusTeamPosition.slot == team_position_slot,
                    BonusTeamPosition.effective_from <= period.end,
                )
                .order_by(BonusTeamPosition.effective_from.desc())
                .first()
            )
            if row is not None:
                team_position_weight = to_decimal(row[0])

        return CalculationContext(
            period=period,
            department_id=department_id,
            department_name=department_name,
            employee_id=employee_id,
            employee_name=employee_name,
            team_id=team_id,
            team_position_slot=team_position_slot,
            team_position_weight=team_position_weight,
            employment_type=employment_type,
            probation_until=probation_until,
            kpi_values=kpi_values,
            revenue_values=revenue_values,
            shifts=shifts,
            monthly_plans=monthly_plans,
        )

    # ------------------------------------------------------------------ #
    def _collect_revenue_sources(self, config: dict[str, Any]) -> list[str]:
        sources: list[str] = []
        if "revenue_source" in config:
            sources.append(config["revenue_source"])
        for comp in config.get("components", []):
            sources.append(comp["source"])
        return sources

    def _load_monthly_plans(self, department_id: str, period: PeriodKey) -> dict[str, Decimal]:
        rows = (
            self.db.query(BonusMonthlyPlan.metric, BonusMonthlyPlan.target_value)
            .filter(
                BonusMonthlyPlan.department_id == department_id,
                BonusMonthlyPlan.year == period.year,
                BonusMonthlyPlan.month == period.month,
            )
            .all()
        )
        return {m: to_decimal(v) for m, v in rows}

    def _resolve_target(
        self,
        kpi_cfg: dict[str, Any],
        monthly_plans: dict[str, Decimal],
    ) -> Optional[Decimal]:
        if "target" in kpi_cfg and kpi_cfg["target"] is not None:
            return to_decimal(kpi_cfg["target"])
        if "target_metric" in kpi_cfg and kpi_cfg["target_metric"]:
            metric = kpi_cfg["target_metric"]
            # The KPI config can reference 'monthly_plan_sales' — strip prefix to get metric name
            if metric.startswith("monthly_plan_"):
                metric = metric[len("monthly_plan_"):]
            return monthly_plans.get(metric)
        return None
