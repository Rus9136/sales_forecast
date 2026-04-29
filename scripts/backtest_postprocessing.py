"""
Backtest пост-обработки прогнозов на out-of-sample данных.

Цель: измерить, как weekend boost (×1.4) и temporal smoothing (±50% от 4-нед
среднего того же weekday) влияют на MAPE/MAE/RMSE по сравнению с raw прогнозом
модели.

Текущая модель (lgbm_model.pkl) обучена в ноябре 2025, поэтому период
2026-02-28..2026-04-28 является честным out-of-sample окном.
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import and_

sys.path.insert(0, "/app")

from app.db import get_db
from app.models.branch import Department, SalesSummary
from app.agents.sales_forecaster_agent import SalesForecasterAgent


BACKTEST_DAYS = 60
MIN_HISTORY_DAYS = 14
SMOOTHING_THRESHOLD = 0.5
WEEKEND_BOOST = 1.4


def main() -> None:
    db = next(get_db())

    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=BACKTEST_DAYS - 1)
    history_start = start_date - timedelta(days=45)

    print(f"Backtest window: {start_date} .. {end_date} ({BACKTEST_DAYS} days)")
    print(f"History fetch from: {history_start}")

    agent = SalesForecasterAgent(model_path="/app/models/lgbm_model.pkl")
    if agent.model is None:
        print("ERROR: model not loaded")
        sys.exit(1)

    trained_at = agent._training_metrics or {}
    print(f"Model loaded. Feature count: {len(agent.feature_columns)}")

    rows = (
        db.query(
            SalesSummary.department_id,
            SalesSummary.date,
            SalesSummary.total_sales,
            Department.name.label("department_name"),
            Department.code.label("department_code"),
            Department.type.label("department_type"),
            Department.segment_type.label("segment_type"),
            Department.parent_id.label("parent_id"),
        )
        .join(Department, SalesSummary.department_id == Department.id)
        .filter(SalesSummary.date >= history_start)
        .filter(SalesSummary.date <= end_date)
        .all()
    )

    if not rows:
        print("ERROR: no sales data in window")
        sys.exit(1)

    df_all = pd.DataFrame(
        [
            {
                "department_id": str(r.department_id),
                "date": r.date,
                "total_sales": float(r.total_sales),
                "department_name": r.department_name,
                "department_code": r.department_code,
                "department_type": r.department_type,
                "segment_type": r.segment_type,
                "parent_id": str(r.parent_id) if r.parent_id else None,
            }
            for r in rows
        ]
    )
    df_all["date"] = pd.to_datetime(df_all["date"])
    df_all = df_all.sort_values(["department_id", "date"]).reset_index(drop=True)

    print(f"Loaded {len(df_all):,} (dept, date) sales rows across "
          f"{df_all['department_id'].nunique()} departments")

    backtest_dates = pd.date_range(start_date, end_date, freq="D").date
    results: list[dict] = []

    for dept_id, dept_df in df_all.groupby("department_id"):
        dept_df = dept_df.sort_values("date").reset_index(drop=True)
        dates_in_dept = set(dept_df["date"].dt.date.tolist())

        for d in backtest_dates:
            if d not in dates_in_dept:
                continue

            actual_row = dept_df[dept_df["date"].dt.date == d].iloc[0]
            actual = actual_row["total_sales"]
            if actual <= 0:
                continue

            hist_window_start = d - timedelta(days=31)
            hist_window_end = d - timedelta(days=1)
            hist = dept_df[
                (dept_df["date"].dt.date >= hist_window_start)
                & (dept_df["date"].dt.date <= hist_window_end)
            ]
            if len(hist) < MIN_HISTORY_DAYS:
                continue

            features = agent._create_prediction_features(d, hist.copy())
            X = pd.DataFrame([features])[agent.feature_columns]
            raw = max(0.0, float(agent.predict(X)[0]))

            python_dow = pd.Timestamp(d).dayofweek
            postgres_dow = (python_dow + 1) % 7
            is_weekend = postgres_dow == 0 or postgres_dow == 6

            with_boost = raw * WEEKEND_BOOST if is_weekend else raw

            same_weekday_window_start = d - timedelta(days=28)
            same_weekday_window_end = d - timedelta(days=1)
            sw = dept_df[
                (dept_df["date"].dt.date >= same_weekday_window_start)
                & (dept_df["date"].dt.date <= same_weekday_window_end)
            ].copy()
            sw["pg_dow"] = ((sw["date"].dt.dayofweek + 1) % 7).astype(int)
            sw_same = sw[sw["pg_dow"] == postgres_dow]

            if len(sw_same) > 0:
                avg_hist = sw_same["total_sales"].mean()
                lo = avg_hist * (1 - SMOOTHING_THRESHOLD)
                hi = avg_hist * (1 + SMOOTHING_THRESHOLD)
                smoothed_raw = float(np.clip(raw, lo, hi))
                smoothed_boost = float(np.clip(with_boost, lo, hi))
            else:
                smoothed_raw = raw
                smoothed_boost = with_boost

            results.append(
                {
                    "dept_id": dept_id,
                    "department_name": actual_row["department_name"],
                    "segment_type": actual_row["segment_type"] or "unknown",
                    "date": d,
                    "is_weekend": is_weekend,
                    "actual": actual,
                    "raw": raw,
                    "boost": with_boost,
                    "smooth": smoothed_raw,
                    "current": smoothed_boost,
                }
            )

    rdf = pd.DataFrame(results)
    print(f"\nTotal predictions: {len(rdf):,}")
    if rdf.empty:
        print("No predictions generated.")
        return

    out_path = "/tmp/backtest_results.csv"
    rdf.to_csv(out_path, index=False)
    print(f"Raw results saved to {out_path}")

    def metrics(actual: pd.Series, pred: pd.Series) -> dict:
        err = pred - actual
        ape = np.abs(err) / actual
        return {
            "MAPE_%": float(ape.mean() * 100),
            "MedianAPE_%": float(ape.median() * 100),
            "MAE": float(np.abs(err).mean()),
            "RMSE": float(np.sqrt((err ** 2).mean())),
            "Bias_%": float(err.mean() / actual.mean() * 100),
        }

    variants = ["raw", "boost", "smooth", "current"]

    print("\n" + "=" * 80)
    print("OVERALL (all departments, all days)")
    print("=" * 80)
    summary = pd.DataFrame({v: metrics(rdf["actual"], rdf[v]) for v in variants}).T
    print(summary.round(2).to_string())

    print("\n" + "=" * 80)
    print("BY DAY TYPE")
    print("=" * 80)
    for label, mask in [("WEEKDAYS", ~rdf["is_weekend"]), ("WEEKENDS", rdf["is_weekend"])]:
        sub = rdf[mask]
        if sub.empty:
            continue
        print(f"\n[{label}]  n={len(sub):,}")
        s = pd.DataFrame({v: metrics(sub["actual"], sub[v]) for v in variants}).T
        print(s.round(2).to_string())

    print("\n" + "=" * 80)
    print("BY SEGMENT TYPE")
    print("=" * 80)
    for seg in sorted(rdf["segment_type"].unique()):
        sub = rdf[rdf["segment_type"] == seg]
        if len(sub) < 30:
            continue
        print(f"\n[{seg}]  n={len(sub):,}, avg_actual={sub['actual'].mean():,.0f}")
        s = pd.DataFrame({v: metrics(sub["actual"], sub[v]) for v in variants}).T
        print(s[["MAPE_%", "MedianAPE_%", "Bias_%"]].round(2).to_string())

    print("\n" + "=" * 80)
    print("BY SCALE (avg daily sales of department)")
    print("=" * 80)
    dept_avg = rdf.groupby("dept_id")["actual"].mean()
    rdf["dept_avg"] = rdf["dept_id"].map(dept_avg)
    rdf["scale_bucket"] = pd.qcut(
        rdf["dept_avg"], q=4,
        labels=["Q1_smallest", "Q2", "Q3", "Q4_largest"],
    )
    for bucket in ["Q1_smallest", "Q2", "Q3", "Q4_largest"]:
        sub = rdf[rdf["scale_bucket"] == bucket]
        if sub.empty:
            continue
        print(f"\n[{bucket}]  n={len(sub):,}, avg_actual={sub['actual'].mean():,.0f}")
        s = pd.DataFrame({v: metrics(sub["actual"], sub[v]) for v in variants}).T
        print(s[["MAPE_%", "MedianAPE_%", "Bias_%"]].round(2).to_string())


if __name__ == "__main__":
    main()
