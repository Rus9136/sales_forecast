"""B2: Hierarchical price elasticity estimation.

Three-level model:
  Level 0 — Global prior (all SKUs pooled)
  Level 1 — Group-level (category × menu_role)
  Level 2 — SKU-level (Grade A/B only, empirical Bayes shrinkage)
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Optional

import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

MIN_GROUP_OBS = 30
MIN_OLS_OBS = 10
CLAMP_LOWER = -3.0
CLAMP_UPPER = 0.0
CONSERVATIVE_CI_FACTOR = 1.2

DATASET_SQL = """
WITH catalog_week AS (
    -- For each (product, dept, week) the real menu price valid that week.
    -- Берём цену БАЗОВОЙ серии (price_type='BASE', без размера) через
    -- DISTINCT ON, а не AVG по размерам: добавление/удаление размера меняло
    -- среднюю без реального изменения цены — фиктивная «вариация», на которой
    -- OLS оценивал ε. Uses sku_catalog_price (orders), NOT derived avg_price.
    SELECT DISTINCT ON (sws.product_id, sws.department_id, sws.week_start)
        sws.product_id,
        sws.department_id,
        sws.week_start,
        sws.total_qty,
        scp.price
    FROM sku_weekly_summary sws
    JOIN sku_catalog_price scp
        ON scp.product_id = sws.product_id
        AND scp.department_id = sws.department_id
        AND scp.date_from <= sws.week_start
        AND scp.date_to > sws.week_start
        AND scp.price > 0
        AND NOT scp.is_stale
    WHERE sws.total_qty > 0
      AND sws.week_start >= :from_date
      AND sws.week_start <= :to_date
    ORDER BY sws.product_id, sws.department_id, sws.week_start,
             (scp.price_type <> 'BASE'), (scp.product_size_id IS NOT NULL),
             scp.product_size_id, scp.id
),
weekly AS (
    SELECT
        cw.product_id,
        cw.department_id,
        cw.week_start,
        cw.total_qty,
        cw.price,
        p.category_id,
        COALESCE(smr.effective_role, 'unknown') AS menu_role
    FROM catalog_week cw
    JOIN product p ON p.id = cw.product_id
    LEFT JOIN sku_menu_role smr
        ON smr.product_id = cw.product_id
        AND smr.department_id = cw.department_id
    WHERE cw.price > 0
),
category_weekly AS (
    SELECT
        category_id,
        week_start,
        SUM(LN(total_qty)) AS sum_log_qty,
        COUNT(*) AS n_rows
    FROM weekly
    GROUP BY category_id, week_start
)
SELECT
    w.product_id,
    w.department_id,
    w.week_start,
    LN(w.total_qty) AS log_qty,
    LN(w.price) AS log_price,
    EXTRACT(MONTH FROM w.week_start)::int AS month,
    (w.week_start - :from_date)::int / 7 AS week_index,
    -- leave-one-out: среднее по категории БЕЗ самого SKU, иначе контроль
    -- частично объясняет зависимую переменную и тянет ε к нулю
    CASE WHEN cw.n_rows > 1
         THEN (cw.sum_log_qty - LN(w.total_qty)) / (cw.n_rows - 1)
         ELSE 0
    END AS cat_log_qty,
    w.category_id,
    w.menu_role
FROM weekly w
LEFT JOIN category_weekly cw
    ON cw.category_id = w.category_id
    AND cw.week_start = w.week_start
ORDER BY w.product_id, w.department_id, w.week_start
"""

GRADE_SQL = """
WITH per_series AS (
    -- Ценовые «режимы» по временной оси для каждой серии (размер × тип цены):
    -- 1 + число реальных смен цены (LAG по date_from). Прежний
    -- COUNT(DISTINCT price) по всем размерам инфлировал грейды: продукт
    -- с 5 размерами по 5 ПОСТОЯННЫМ ценам получал n_events=5 → Grade A
    -- без единого реального изменения цены.
    -- Only intervals overlapping the lookback window (date_to > :from_date):
    -- prices that expired before the window carry no usable signal.
    SELECT product_id, department_id, product_size_id, price_type,
           1 + COUNT(*) FILTER (
               WHERE prev_price IS NOT NULL AND price <> prev_price
           ) AS n_regimes
    FROM (
        SELECT product_id, department_id, product_size_id, price_type, price,
               LAG(price) OVER (
                   PARTITION BY product_id, department_id, product_size_id, price_type
                   ORDER BY date_from, id
               ) AS prev_price
        FROM sku_catalog_price
        WHERE product_id IS NOT NULL AND price > 0
          AND date_to > :from_date
          AND NOT is_stale
    ) t
    GROUP BY product_id, department_id, product_size_id, price_type
),
variation AS (
    SELECT product_id, department_id, MAX(n_regimes) AS n_events
    FROM per_series
    GROUP BY product_id, department_id
),
sales_span AS (
    SELECT product_id, department_id,
        COUNT(DISTINCT sale_date) AS n_days
    FROM sku_daily_sales
    WHERE sale_date >= :from_date
    GROUP BY product_id, department_id
)
SELECT
    COALESCE(v.product_id, s.product_id) AS product_id,
    COALESCE(v.department_id, s.department_id) AS department_id,
    COALESCE(v.n_events, 0) AS n_events,
    COALESCE(s.n_days, 0) AS n_days
FROM variation v
FULL OUTER JOIN sales_span s
    ON s.product_id = v.product_id AND s.department_id = v.department_id
"""


def _assign_grade(n_events: int, n_days: int) -> str:
    """n_events = number of price REGIMES over time for the base series
    (1 + real price changes), not distinct values across sizes."""
    if n_events >= 5 and n_days >= 90:
        return "A"
    if n_events >= 4 and n_days >= 60:
        return "B"
    if n_events >= 3:
        return "C"
    return "D"


def _run_ols(X: np.ndarray, y: np.ndarray, extra_dof: int = 0):
    """OLS regression. Returns (beta, se, r_squared, n, k).

    extra_dof — параметры, поглощённые вне матрицы (например, fixed effects
    при within-преобразовании): уменьшают остаточные степени свободы для SE.
    """
    n, k = X.shape
    if n <= k + extra_dof:
        return None, None, None, n, k

    try:
        beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    except np.linalg.LinAlgError:
        return None, None, None, n, k

    y_hat = X @ beta
    resid = y - y_hat
    ss_res = np.sum(resid ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)

    if ss_tot == 0:
        return beta, np.zeros(k), 0.0, n, k

    r_squared = 1.0 - ss_res / ss_tot
    s_sq = ss_res / max(n - k - extra_dof, 1)

    try:
        XtX_inv = np.linalg.inv(X.T @ X)
        var_beta = s_sq * XtX_inv
        se = np.sqrt(np.clip(np.diag(var_beta), 0, None))
    except np.linalg.LinAlgError:
        se = np.full(k, np.nan)

    return beta, se, r_squared, n, k


def _build_design_matrix(df: pd.DataFrame, within: bool = False):
    """Build OLS design matrix: intercept + log_price + month dummies + trend + cat_control.

    within=True — within-преобразование (fixed effects по паре SKU×dept):
    все регрессоры и y деминятся по паре, ε идентифицируется только из
    ВРЕМЕННОЙ вариации цен (реальные изменения приказами), а не из
    межпозиционных различий уровней цен. Возвращаемый extra_dof — число
    поглощённых средних (n_pairs − 1) для честных SE.
    """
    n = len(df)
    month_dummies = pd.get_dummies(df["month"], prefix="m", drop_first=True, dtype=float)

    mat = pd.DataFrame(
        np.column_stack([
            df["log_price"].values.astype(float),
            month_dummies.values,
            df["week_index"].values.astype(float),
            df["cat_log_qty"].values.astype(float),
        ]),
        index=df.index,
    )
    y = pd.Series(df["log_qty"].values.astype(float), index=df.index)

    extra_dof = 0
    if within:
        groups = (df["product_id"].astype(str) + "|" + df["department_id"].astype(str)).values
        mat = mat - mat.groupby(groups).transform("mean")
        y = y - y.groupby(groups).transform("mean")
        extra_dof = len(np.unique(groups)) - 1

    X = np.column_stack([np.ones(n), mat.values])
    col_names = ["intercept", "log_price"] + list(month_dummies.columns) + ["trend", "cat_log_qty"]
    return X, y.values, col_names, extra_dof


class ElasticityEstimationService:
    def __init__(self, db: Session):
        self.db = db

    def estimate_all(self, lookback_days: int = 730) -> dict:
        """Run full 3-level elasticity estimation."""
        from datetime import timedelta
        today = date.today()
        from_date = today - timedelta(days=lookback_days)
        to_date = today
        version = datetime.now().isoformat()

        logger.info("Loading regression dataset from %s to %s", from_date, to_date)
        df = pd.read_sql(
            text(DATASET_SQL),
            self.db.bind,
            params={"from_date": from_date, "to_date": to_date},
        )
        if df.empty:
            logger.warning("No data for elasticity estimation")
            return {"status": "no_data", "total": 0}

        logger.info("Dataset: %d rows, %d unique SKU×dept pairs", len(df), df.groupby(["product_id", "department_id"]).ngroups)

        grades_df = pd.read_sql(
            text(GRADE_SQL),
            self.db.bind,
            params={"from_date": from_date},
        )
        grades_df["grade"] = grades_df.apply(lambda r: _assign_grade(r["n_events"], r["n_days"]), axis=1)

        df["group_key"] = df["category_id"].astype(str) + ":" + df["menu_role"]

        global_est = self._estimate_global(df)
        logger.info("Global prior: ε=%.4f (SE=%.4f, R²=%.4f)", global_est["epsilon"], global_est["se"], global_est["r_squared"])

        group_estimates = self._estimate_groups(df)
        logger.info("Group-level estimates: %d groups", len(group_estimates))

        sku_estimates, tau_sq_by_group = self._estimate_sku_level(df, grades_df, group_estimates)
        logger.info("SKU-level estimates (Grade A/B): %d", len(sku_estimates))

        results = self._assign_all(
            df, grades_df, global_est, group_estimates, sku_estimates,
            tau_sq_by_group, version,
        )
        logger.info("Total elasticity assignments: %d", len(results))

        n_upserted = self._upsert(results, version)
        logger.info("Upserted %d elasticity records", n_upserted)

        grade_dist = {}
        level_dist = {}
        for r in results:
            grade_dist[r["reliability_grade"]] = grade_dist.get(r["reliability_grade"], 0) + 1
            level_dist[r["estimation_level"]] = level_dist.get(r["estimation_level"], 0) + 1

        return {
            "status": "ok",
            "total": len(results),
            "upserted": n_upserted,
            "global_prior": float(global_est["epsilon"]),
            "groups_estimated": len(group_estimates),
            "by_grade": grade_dist,
            "by_level": level_dist,
            "model_version": version,
        }

    def _estimate_global(self, df: pd.DataFrame) -> dict:
        # within-оценка: ε только из временной вариации цен (FE по паре SKU×dept)
        X, y, col_names, extra_dof = _build_design_matrix(df, within=True)
        beta, se, r_sq, n, k = _run_ols(X, y, extra_dof)

        if beta is None:
            # деградация: фейковый prior помечается явно, а не выдаётся за оценку
            return {"epsilon": -1.0, "se": 0.5, "r_squared": 0.0, "n": n, "degraded": True}

        eps_idx = col_names.index("log_price")
        t_crit = stats.t.ppf(0.975, df=max(n - k - extra_dof, 1))

        return {
            "epsilon": float(np.clip(beta[eps_idx], CLAMP_LOWER, CLAMP_UPPER)),
            "se": float(se[eps_idx]),
            "ci_lower": float(np.clip(beta[eps_idx] - t_crit * se[eps_idx], CLAMP_LOWER, CLAMP_UPPER)),
            "ci_upper": float(np.clip(beta[eps_idx] + t_crit * se[eps_idx], CLAMP_LOWER, CLAMP_UPPER)),
            "r_squared": float(r_sq) if r_sq is not None else 0.0,
            "n": n,
        }

    def _estimate_groups(self, df: pd.DataFrame) -> dict[str, dict]:
        results = {}
        for gk, gdf in df.groupby("group_key"):
            if len(gdf) < MIN_GROUP_OBS:
                continue
            # within-оценка: межпозиционные различия уровней цен не загрязняют ε
            X, y, col_names, extra_dof = _build_design_matrix(gdf, within=True)
            beta, se, r_sq, n, k = _run_ols(X, y, extra_dof)
            if beta is None:
                continue

            eps_idx = col_names.index("log_price")
            if np.isnan(se[eps_idx]) or se[eps_idx] == 0:
                continue

            t_crit = stats.t.ppf(0.975, df=max(n - k - extra_dof, 1))
            results[gk] = {
                "epsilon": float(np.clip(beta[eps_idx], CLAMP_LOWER, CLAMP_UPPER)),
                "se": float(se[eps_idx]),
                "ci_lower": float(np.clip(beta[eps_idx] - t_crit * se[eps_idx], CLAMP_LOWER, CLAMP_UPPER)),
                "ci_upper": float(np.clip(beta[eps_idx] + t_crit * se[eps_idx], CLAMP_LOWER, CLAMP_UPPER)),
                "r_squared": float(r_sq) if r_sq is not None else 0.0,
                "n": n,
            }
        return results

    def _estimate_sku_level(
        self,
        df: pd.DataFrame,
        grades_df: pd.DataFrame,
        group_estimates: dict[str, dict],
    ) -> tuple[dict[tuple, dict], dict[str, float]]:
        """Two-pass empirical Bayes: raw per-SKU OLS, then shrinkage toward
        the group estimate with tau² from the spread of raw SKU epsilons
        WITHIN the group (between-SKU heterogeneity).

        Возвращает (sku_estimates, tau_sq_by_group) — τ² нужна и дальше:
        консервативный край CI для Grade C/D строится как предиктивный
        интервал sqrt(SE² + τ²), а не sampling-CI пулированного коэффициента.
        """
        # Grade A/B only: SKU-оценка на 3 реальных ценах (Grade C) почти
        # неизбежно шумная — C планируется по group-уровню с широким CI
        eligible = {
            (int(r["product_id"]), str(r["department_id"]))
            for _, r in grades_df[grades_df["grade"].isin(["A", "B"])].iterrows()
        }

        # Pass 1: raw OLS per eligible SKU×dept
        raw: dict[tuple, dict] = {}
        for (pid, did), sdf in df.groupby(["product_id", "department_id"]):
            key = (int(pid), str(did))
            if key not in eligible or len(sdf) < MIN_OLS_OBS:
                continue

            # одна пара: FE эквивалентен intercept — within не нужен
            X, y, col_names, _ = _build_design_matrix(sdf)
            # остаточные dof ≥ 10: матрица до ~15 колонок, пары с n чуть выше
            # MIN_OLS_OBS давали оценки на 1-5 степенях свободы
            if X.shape[0] - X.shape[1] < 10:
                continue
            beta, se, r_sq, n, k = _run_ols(X, y)
            if beta is None:
                continue

            eps_idx = col_names.index("log_price")
            if np.isnan(se[eps_idx]) or se[eps_idx] == 0:
                continue

            raw[key] = {
                "eps": float(beta[eps_idx]),
                "se": float(se[eps_idx]),
                "r_squared": float(r_sq) if r_sq is not None else 0.0,
                "n": n,
                "k": k,
                "group_key": sdf["group_key"].iloc[0],
            }

        # tau² per group: var of raw SKU epsilons minus mean sampling variance.
        # Сырые ε винзоризуются: единичные выбросы (+7, −40) взрывали var,
        # w→1 и shrinkage отключался ровно на самых шумных группах.
        tau_sq_by_group: dict[str, float] = {}
        by_group: dict[str, list[dict]] = {}
        for est in raw.values():
            by_group.setdefault(est["group_key"], []).append(est)
        for gk, ests in by_group.items():
            if len(ests) >= 2:
                eps_wins = np.clip([e["eps"] for e in ests], -4.0, 1.0)
                var_across = float(np.var(eps_wins))
                mean_se_sq = float(np.mean([e["se"] ** 2 for e in ests]))
                tau_sq_by_group[gk] = max(var_across - mean_se_sq, 0.001)

        # Pass 2: shrink toward group estimate
        results = {}
        for key, est in raw.items():
            gk = est["group_key"]
            group_est = group_estimates.get(gk)
            if group_est:
                tau_sq = tau_sq_by_group.get(gk, group_est["se"] ** 2)
                eps_shrunk, se_shrunk = self._shrink(
                    est["eps"], est["se"], group_est["epsilon"], tau_sq
                )
            else:
                eps_shrunk = est["eps"]
                se_shrunk = est["se"]

            t_crit = stats.t.ppf(0.975, df=max(est["n"] - est["k"], 1))
            results[key] = {
                "epsilon": float(np.clip(eps_shrunk, CLAMP_LOWER, CLAMP_UPPER)),
                "se": float(se_shrunk),
                "ci_lower": float(np.clip(eps_shrunk - t_crit * se_shrunk, CLAMP_LOWER, CLAMP_UPPER)),
                "ci_upper": float(np.clip(eps_shrunk + t_crit * se_shrunk, CLAMP_LOWER, CLAMP_UPPER)),
                "r_squared": est["r_squared"],
                "n": est["n"],
                "group_key": gk,
            }

        return results, tau_sq_by_group

    def _shrink(
        self,
        eps_sku: float,
        se_sku: float,
        eps_group: float,
        tau_sq: float,
    ) -> tuple[float, float]:
        """Empirical Bayes shrinkage toward group mean."""
        tau_sq = max(tau_sq, 1e-8)
        w = tau_sq / (tau_sq + se_sku ** 2)
        eps_shrunk = w * eps_sku + (1 - w) * eps_group
        se_shrunk = np.sqrt(1.0 / (1.0 / max(se_sku ** 2, 1e-8) + 1.0 / tau_sq))

        return float(eps_shrunk), float(se_shrunk)

    def _assign_all(
        self,
        df: pd.DataFrame,
        grades_df: pd.DataFrame,
        global_est: dict,
        group_estimates: dict[str, dict],
        sku_estimates: dict[tuple, dict],
        tau_sq_by_group: dict[str, float],
        version: str,
    ) -> list[dict]:
        pairs = df.groupby(["product_id", "department_id"]).first().reset_index()
        grade_map = {
            (int(r["product_id"]), str(r["department_id"])): (r["grade"], int(r["n_events"]))
            for _, r in grades_df.iterrows()
        }

        # глобальная межгрупповая гетерогенность — fallback τ² для групп,
        # где SKU-оценок не хватило (и для level='global')
        group_eps = [g["epsilon"] for g in group_estimates.values()]
        tau_global_sq = float(np.var(np.clip(group_eps, -4.0, 1.0))) if len(group_eps) >= 2 else 0.25
        tau_global_sq = max(tau_global_sq, 0.09)  # floor: sd ≥ 0.3

        results = []
        for _, row in pairs.iterrows():
            pid = int(row["product_id"])
            did = str(row["department_id"])
            key = (pid, did)
            gk = row["group_key"]
            grade, n_events = grade_map.get(key, ("D", 0))

            if key in sku_estimates and grade in ("A", "B"):
                est = sku_estimates[key]
                level = "sku"
            elif gk in group_estimates:
                est = group_estimates[gk]
                level = "group"
            else:
                est = global_est
                level = "global"

            eps = est["epsilon"]
            se = est["se"]
            ci_lo = est.get("ci_lower", eps - 1.96 * se)
            ci_hi = est.get("ci_upper", eps + 1.96 * se)

            if grade in ("C", "D") and level != "sku":
                # Предиктивный интервал для КОНКРЕТНОГО SKU: sampling-CI
                # пулированного коэффициента при n в тысячи имеет ширину ≈ 0,
                # межпозиционная гетерогенность τ² обязана входить в
                # консервативный край — иначе ci_lower ≈ mean и «планирование
                # по консервативному краю» не работает.
                tau_sq = (
                    tau_sq_by_group.get(gk, tau_global_sq)
                    if level == "group" else tau_global_sq
                )
                spread = 1.96 * float(np.sqrt(se ** 2 + tau_sq))
                ci_lo = max(eps - spread, CLAMP_LOWER)
                ci_hi = min(eps + spread, CLAMP_UPPER)

            positive_eps_overridden = None
            if eps >= 0:
                positive_eps_overridden = round(float(eps), 4)
                eps = -0.1
                ci_lo = -0.5
                ci_hi = 0.0
                grade = "D"
                level = "global" if level == "sku" else level

            diagnostics = {"global_prior": round(global_est["epsilon"], 4)}
            if positive_eps_overridden is not None:
                diagnostics["positive_eps_overridden"] = positive_eps_overridden
            if global_est.get("degraded"):
                diagnostics["global_prior_degraded"] = True

            MAX_VAL = 9999.0
            results.append({
                "product_id": pid,
                "department_id": did,
                "elasticity_mean": round(max(min(eps, MAX_VAL), -MAX_VAL), 4),
                "elasticity_ci_lower": round(max(min(ci_lo, MAX_VAL), -MAX_VAL), 4),
                "elasticity_ci_upper": round(max(min(ci_hi, MAX_VAL), -MAX_VAL), 4),
                "elasticity_se": round(max(min(se, MAX_VAL), 0), 4),
                "n_price_events": n_events,
                "n_observations": int(est.get("n", 0)),
                "estimation_level": level,
                "reliability_grade": grade,
                "group_key": gk,
                "model_r_squared": round(max(min(est.get("r_squared", 0.0), 9.9999), -9.9999), 4),
                "model_version": version,
                "diagnostics": diagnostics,
            })

        return results

    def _upsert(self, results: list[dict], version: Optional[str] = None) -> int:
        if not results:
            return 0

        import json

        CHUNK = 500
        total = 0
        for i in range(0, len(results), CHUNK):
            chunk = results[i:i + CHUNK]
            values_parts = []
            params: dict[str, Any] = {}
            for j, r in enumerate(chunk):
                prefix = f"v{j}"
                values_parts.append(
                    f"(:{prefix}_pid, CAST(:{prefix}_did AS uuid), :{prefix}_mean, "
                    f":{prefix}_ci_lo, :{prefix}_ci_hi, :{prefix}_se, "
                    f":{prefix}_ne, :{prefix}_no, :{prefix}_level, "
                    f":{prefix}_grade, :{prefix}_gk, :{prefix}_r2, "
                    f":{prefix}_ver, CAST(:{prefix}_diag AS jsonb))"
                )
                params[f"{prefix}_pid"] = r["product_id"]
                params[f"{prefix}_did"] = r["department_id"]
                params[f"{prefix}_mean"] = r["elasticity_mean"]
                params[f"{prefix}_ci_lo"] = r["elasticity_ci_lower"]
                params[f"{prefix}_ci_hi"] = r["elasticity_ci_upper"]
                params[f"{prefix}_se"] = r["elasticity_se"]
                params[f"{prefix}_ne"] = r["n_price_events"]
                params[f"{prefix}_no"] = r["n_observations"]
                params[f"{prefix}_level"] = r["estimation_level"]
                params[f"{prefix}_grade"] = r["reliability_grade"]
                params[f"{prefix}_gk"] = r["group_key"]
                params[f"{prefix}_r2"] = r["model_r_squared"]
                params[f"{prefix}_ver"] = r["model_version"]
                params[f"{prefix}_diag"] = json.dumps(r.get("diagnostics", {}))

            sql = f"""
                INSERT INTO sku_elasticity
                    (product_id, department_id, elasticity_mean,
                     elasticity_ci_lower, elasticity_ci_upper, elasticity_se,
                     n_price_events, n_observations, estimation_level,
                     reliability_grade, group_key, model_r_squared,
                     model_version, diagnostics)
                VALUES {', '.join(values_parts)}
                ON CONFLICT (product_id, department_id) DO UPDATE SET
                    elasticity_mean = EXCLUDED.elasticity_mean,
                    elasticity_ci_lower = EXCLUDED.elasticity_ci_lower,
                    elasticity_ci_upper = EXCLUDED.elasticity_ci_upper,
                    elasticity_se = EXCLUDED.elasticity_se,
                    n_price_events = EXCLUDED.n_price_events,
                    n_observations = EXCLUDED.n_observations,
                    estimation_level = EXCLUDED.estimation_level,
                    reliability_grade = EXCLUDED.reliability_grade,
                    group_key = EXCLUDED.group_key,
                    model_r_squared = EXCLUDED.model_r_squared,
                    model_version = EXCLUDED.model_version,
                    diagnostics = EXCLUDED.diagnostics,
                    updated_at = NOW()
            """
            self.db.execute(text(sql), params)
            total += len(chunk)

        if version is not None:
            # пары, выпавшие из ассортимента/окна, не должны вечно хранить
            # старую ε: потребители не фильтруют по свежести model_version,
            # а отсутствие записи даёт честный консервативный fallback −1.0
            stale = self.db.execute(
                text("DELETE FROM sku_elasticity WHERE model_version <> :ver"),
                {"ver": version},
            )
            if stale.rowcount:
                logger.info("Removed %d stale elasticity rows (old model_version)", stale.rowcount)

        self.db.commit()
        return total
