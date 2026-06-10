"""Labor-demand signal for TCO (Time Tracking).

Sales Forecast is the demand-signal provider only — TCO owns the solver,
demand_by_role and its own LLM agents. This service builds the read-only
enrichment payloads consumed by TCO's agents.

See docs/LABOR_OPTIMIZATION_ARCHITECTURE.md §2.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..agents.sku_forecaster_agent import get_sku_forecaster_agent
from ..agents.sales_forecaster_agent import get_forecaster_agent

logger = logging.getLogger(__name__)


def _share(value: float, total: float) -> float:
    return round(value / total, 4) if total else 0.0


def _sane_margin(value) -> Optional[float]:
    """Keep gp_margin only inside the plausible [0, 1] band.

    Upstream cost data is incomplete for some SKUs, producing absurd raw
    margins (e.g. -5.37 = cost 6.4x revenue, or 1.0 = missing cost). We null
    those out rather than ship an untrustworthy per-item signal — matching the
    consumer's own 0–100% guard. `data_quality.cost_coverage` is the aggregate
    flag.
    """
    if value is None:
        return None
    try:
        m = float(value)
    except (TypeError, ValueError):
        return None
    return m if 0.0 <= m <= 1.0 else None


class LaborDemandService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # §2.1 menu-mix
    # ------------------------------------------------------------------

    def menu_mix(
        self,
        department_id: str,
        from_date: date,
        to_date: date,
        top_n: int = 25,
    ) -> dict:
        """Menu intelligence: role distribution, top dishes, category load.

        Raises LookupError if the department does not exist.
        """
        dept = self._department(department_id)
        if dept is None:
            raise LookupError("Department not found")
        dept_name = dept.name

        agent = get_sku_forecaster_agent()
        sku_model_trained = agent.model is not None
        data_quality = self._menu_data_quality(department_id, sku_model_trained)

        period = {"from": str(from_date), "to": str(to_date)}

        # Without a trained SKU model we cannot produce predicted_qty.
        # Return an empty-but-valid payload so TCO degrades gracefully.
        if not sku_model_trained:
            logger.warning("menu_mix: SKU model not trained, returning empty payload")
            return {
                "department_id": department_id,
                "department_name": dept_name,
                "period": period,
                "role_distribution": {},
                "top_dishes": [],
                "category_load": [],
                "data_quality": data_quality,
            }

        # Price comes from realised receipts (sku_weekly_summary.avg_price =
        # revenue/qty), NOT product.default_sale_price — the latter is far too
        # sparse on some iiko domains (~2% coverage), which collapses
        # revenue_share to a single SKU. Forecast avg_price is the fallback.
        price_map = self._price_map(department_id)

        # Aggregate the SKU forecast across every day in the period.
        # top_n=None → forecast all active SKUs (needed for role/category shares).
        agg: dict[int, dict] = {}
        d = from_date
        while d <= to_date:
            for it in agent.forecast_department_skus(department_id, d, self.db, top_n=None):
                pid = it["product_id"]
                a = agg.get(pid)
                if a is None:
                    a = agg[pid] = {
                        "product_name": it["product_name"],
                        "product_type": it["product_type"],
                        "group_name": it.get("group_name"),
                        "category_name": it.get("category_name"),
                        "fc_price": it.get("avg_price"),
                        "qty": 0.0,
                    }
                a["qty"] += it.get("predicted_qty") or 0.0
                if a["fc_price"] is None and it.get("avg_price") is not None:
                    a["fc_price"] = it["avg_price"]
            d += timedelta(days=1)

        # Resolve price (realised first, forecast fallback) and derive revenue.
        for pid, a in agg.items():
            price = price_map.get(pid)
            if price is None:
                price = a.get("fc_price")
            a.pop("fc_price", None)
            a["avg_price"] = round(price, 2) if price else None
            a["revenue"] = a["qty"] * price if price else 0.0

        total_qty = sum(a["qty"] for a in agg.values())
        total_rev = sum(a["revenue"] for a in agg.values())
        roles = self._menu_roles(department_id)

        return {
            "department_id": department_id,
            "department_name": dept_name,
            "period": period,
            "role_distribution": self._role_distribution(agg, roles, total_qty, total_rev),
            "top_dishes": self._top_dishes(agg, roles, total_qty, total_rev, top_n),
            "category_load": self._category_load(agg, total_qty),
            "data_quality": data_quality,
        }

    # ------------------------------------------------------------------
    # §2.2 forecast
    # ------------------------------------------------------------------

    def forecast_signal(
        self,
        department_id: str,
        from_date: date,
        to_date: date,
    ) -> dict:
        """Daily demand signal + intraday revenue curve.

        Raises LookupError if the department does not exist.
        """
        dept = self._department(department_id)
        if dept is None:
            raise LookupError("Department not found")

        forecaster = get_forecaster_agent()
        model_version = str(getattr(forecaster, "_trained_at", "unknown") or "unknown")

        sku_agent = get_sku_forecaster_agent()
        sku_trained = sku_agent.model is not None

        avg_receipt = self._avg_receipt_sum(department_id)
        today = date.today()
        hourly_cache: dict[int, list] = {}

        days = []
        d = from_date
        while d <= to_date:
            try:
                revenue = forecaster.forecast(department_id, d, self.db)
            except Exception as exc:  # noqa: BLE001 — a bad day must not fail the range
                logger.warning("forecast_signal: %s on %s failed: %s", department_id, d, exc)
                revenue = None

            receipts = (
                int(round(revenue / avg_receipt))
                if revenue and avg_receipt else None
            )

            total_qty = None
            if sku_trained:
                items = sku_agent.forecast_department_skus(department_id, d, self.db, top_n=None)
                total_qty = round(sum(it.get("predicted_qty") or 0.0 for it in items), 1)

            pg_dow = (d.weekday() + 1) % 7
            if pg_dow not in hourly_cache:
                hourly_cache[pg_dow] = self._hourly_profile(department_id, pg_dow)

            days.append({
                "date": str(d),
                "day_of_week": d.strftime("%A").lower(),
                "is_weekend": pg_dow in (0, 6),
                "predicted_revenue": round(revenue, 2) if revenue else None,
                "predicted_receipts": receipts,
                "predicted_total_qty": total_qty,
                "confidence": "high" if (d - today).days <= 7 else "medium",
                "hourly_profile": hourly_cache[pg_dow],
            })
            d += timedelta(days=1)

        return {
            "department_id": department_id,
            "department_name": dept.name,
            "segment_type": dept.segment_type,
            "model_version": model_version,
            "days": days,
        }

    # ------------------------------------------------------------------
    # §2.3 elasticity-signal
    # ------------------------------------------------------------------

    def elasticity_signal(
        self,
        department_id: str,
        grades: Optional[list[str]] = None,
    ) -> dict:
        """Per-SKU elasticity for a department + network global prior.

        Ordered least-elastic first (closest to 0 → least price/quality
        sensitive → where staffing cuts hurt revenue most).
        Raises LookupError if the department does not exist.
        """
        if self._department(department_id) is None:
            raise LookupError("Department not found")

        global_prior = self.db.execute(text(
            "SELECT elasticity_mean FROM sku_elasticity WHERE estimation_level = 'global' LIMIT 1"
        )).scalar()

        conditions = ["se.department_id = CAST(:dept AS uuid)"]
        params: dict = {"dept": department_id}
        if grades:
            conditions.append("se.reliability_grade = ANY(:grades)")
            params["grades"] = grades
        where = " AND ".join(conditions)

        rows = self.db.execute(text(f"""
            SELECT se.product_id, p.name AS product_name,
                   mr.effective_role AS menu_role,
                   se.elasticity_mean, se.reliability_grade, se.estimation_level
            FROM sku_elasticity se
            LEFT JOIN product p ON p.id = se.product_id
            LEFT JOIN sku_menu_role mr
                ON mr.product_id = se.product_id
               AND mr.department_id = se.department_id
            WHERE {where}
            ORDER BY ABS(se.elasticity_mean) ASC
        """), params).fetchall()

        return {
            "department_id": department_id,
            "global_prior": float(global_prior) if global_prior is not None else None,
            "items": [
                {
                    "product_id": r.product_id,
                    "product_name": r.product_name,
                    "menu_role": r.menu_role,
                    "elasticity_mean": float(r.elasticity_mean),
                    "reliability_grade": r.reliability_grade,
                    "estimation_level": r.estimation_level,
                }
                for r in rows
            ],
        }

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _department(self, department_id: str):
        return self.db.execute(
            text("SELECT name, segment_type FROM departments WHERE id = CAST(:did AS uuid)"),
            {"did": department_id},
        ).fetchone()

    def _avg_receipt_sum(self, department_id: str) -> Optional[float]:
        row = self.db.execute(text("""
            SELECT avg_receipt_sum
            FROM department_weekly_summary
            WHERE department_id = CAST(:dept AS uuid)
              AND avg_receipt_sum IS NOT NULL
            ORDER BY week_start DESC
            LIMIT 1
        """), {"dept": department_id}).fetchone()
        return float(row.avg_receipt_sum) if row and row.avg_receipt_sum else None

    def _hourly_profile(self, department_id: str, pg_dow: int, lookback_weeks: int = 8) -> list:
        """Historical revenue share by hour for a weekday (sales_by_hour avg)."""
        cutoff = date.today() - timedelta(weeks=lookback_weeks)
        rows = self.db.execute(text("""
            SELECT hour, AVG(sales_amount) AS avg_amt
            FROM sales_by_hour
            WHERE department_id = CAST(:dept AS uuid)
              AND date >= :cutoff
              AND EXTRACT(DOW FROM date) = :pg_dow
            GROUP BY hour
            ORDER BY hour
        """), {"dept": department_id, "cutoff": cutoff, "pg_dow": pg_dow}).fetchall()
        total = sum(float(r.avg_amt or 0.0) for r in rows)
        if total <= 0:
            return []
        return [
            {"hour": int(r.hour), "revenue_share": round(float(r.avg_amt or 0.0) / total, 4)}
            for r in rows
        ]

    def _menu_roles(self, department_id: str) -> dict[int, dict]:
        """product_id → {role, gp_margin, demand_cv} from sku_menu_role.

        features holds RAW values (clustering normalises on a copy), so
        gp_margin / demand_cv are usable as-is.
        """
        rows = self.db.execute(text("""
            SELECT product_id, effective_role, features
            FROM sku_menu_role
            WHERE department_id = CAST(:dept AS uuid)
        """), {"dept": department_id}).fetchall()
        out: dict[int, dict] = {}
        for r in rows:
            feats = r.features or {}
            out[r.product_id] = {
                "role": r.effective_role,
                "gp_margin": _sane_margin(feats.get("gp_margin")),
                "demand_cv": feats.get("demand_cv"),
            }
        return out

    def _price_map(self, department_id: str) -> dict[int, float]:
        """product_id → latest realised avg_price (revenue/qty) from sku_weekly_summary."""
        rows = self.db.execute(text("""
            SELECT DISTINCT ON (product_id) product_id, avg_price
            FROM sku_weekly_summary
            WHERE department_id = CAST(:dept AS uuid)
              AND avg_price IS NOT NULL AND avg_price > 0
            ORDER BY product_id, week_start DESC
        """), {"dept": department_id}).fetchall()
        return {r.product_id: float(r.avg_price) for r in rows}

    @staticmethod
    def _role_distribution(agg, roles, total_qty, total_rev) -> dict:
        buckets: dict[str, dict] = {}
        for pid, a in agg.items():
            role = (roles.get(pid) or {}).get("role") or "unclassified"
            b = buckets.setdefault(role, {"sku_count": 0, "qty": 0.0, "revenue": 0.0})
            b["sku_count"] += 1
            b["qty"] += a["qty"]
            b["revenue"] += a["revenue"]
        return {
            role: {
                "sku_count": b["sku_count"],
                "qty_share": _share(b["qty"], total_qty),
                "revenue_share": _share(b["revenue"], total_rev),
            }
            for role, b in sorted(buckets.items(), key=lambda kv: kv[1]["qty"], reverse=True)
        }

    @staticmethod
    def _top_dishes(agg, roles, total_qty, total_rev, top_n) -> list:
        ranked = sorted(agg.items(), key=lambda kv: kv[1]["qty"], reverse=True)[:top_n]
        dishes = []
        for rank, (pid, a) in enumerate(ranked, start=1):
            rinfo = roles.get(pid) or {}
            dishes.append({
                "product_id": pid,
                "product_name": a["product_name"],
                "product_type": a["product_type"],
                "category_name": a["category_name"],
                "group_name": a["group_name"],
                "menu_role": rinfo.get("role"),
                "predicted_qty": round(a["qty"], 1),
                "qty_share": _share(a["qty"], total_qty),
                "revenue_share": _share(a["revenue"], total_rev),
                "avg_price": a["avg_price"],
                "gp_margin": rinfo.get("gp_margin"),
                "demand_cv": rinfo.get("demand_cv"),
                "rank": rank,
            })
        return dishes

    @staticmethod
    def _category_load(agg, total_qty) -> list:
        cats: dict[Optional[str], dict] = {}
        for a in agg.values():
            c = cats.setdefault(a["category_name"], {"qty": 0.0, "sku_count": 0})
            c["qty"] += a["qty"]
            c["sku_count"] += 1
        return [
            {
                "category_name": name,
                "predicted_qty": round(c["qty"], 1),
                "qty_share": _share(c["qty"], total_qty),
                "sku_count": c["sku_count"],
            }
            for name, c in sorted(cats.items(), key=lambda kv: kv[1]["qty"], reverse=True)
        ]

    def _menu_data_quality(self, department_id: str, sku_model_trained: bool) -> dict:
        cov = self.db.execute(text("""
            SELECT cost_coverage
            FROM department_weekly_summary
            WHERE department_id = CAST(:dept AS uuid)
            ORDER BY week_start DESC
            LIMIT 1
        """), {"dept": department_id}).fetchone()

        meta = self.db.execute(text("""
            SELECT cluster_meta
            FROM sku_menu_role
            WHERE department_id = CAST(:dept AS uuid)
              AND cluster_meta IS NOT NULL
            ORDER BY updated_at DESC
            LIMIT 1
        """), {"dept": department_id}).fetchone()

        silhouette = run_date = None
        if meta and meta.cluster_meta:
            silhouette = meta.cluster_meta.get("silhouette")
            run_date = meta.cluster_meta.get("run_date")

        return {
            "cost_coverage": float(cov.cost_coverage) if cov and cov.cost_coverage is not None else None,
            "clustering_silhouette": silhouette,
            "menu_roles_run_date": run_date,
            "sku_model_trained": sku_model_trained,
        }
