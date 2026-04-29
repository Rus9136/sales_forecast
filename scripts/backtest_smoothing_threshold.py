"""
Подбор оптимального threshold для temporal smoothing.

После удаления weekend boost (этап 1.1), single-knob осталась — это threshold
для _apply_temporal_smoothing. Сейчас 0.5 (±50% от 4-нед среднего того же weekday).

Гипотеза: текущий 0.5 слишком тугой и обрезает реальные вариации.
Проверим: 0.3 / 0.5 / 0.75 / 1.0 / 1.5 / 2.0 / 3.0 / off.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta

import numpy as np
import pandas as pd

sys.path.insert(0, "/app")

from app.db import get_db
from app.models.branch import Department, SalesSummary
from app.agents.sales_forecaster_agent import SalesForecasterAgent


BACKTEST_DAYS = 60
MIN_HISTORY_DAYS = 14
THRESHOLDS = [0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, None]  # None = off


def main() -> None:
    db = next(get_db())

    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=BACKTEST_DAYS - 1)
    history_start = start_date - timedelta(days=45)

    print(f"Backtest window: {start_date} .. {end_date} ({BACKTEST_DAYS} days)")

    agent = SalesForecasterAgent(model_path="/app/models/lgbm_model.pkl")
    if agent.model is None:
        print("ERROR: model not loaded")
        sys.exit(1)

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

            sw_window_start = d - timedelta(days=28)
            sw_window_end = d - timedelta(days=1)
            sw = dept_df[
                (dept_df["date"].dt.date >= sw_window_start)
                & (dept_df["date"].dt.date <= sw_window_end)
            ].copy()
            sw["pg_dow"] = ((sw["date"].dt.dayofweek + 1) % 7).astype(int)
            sw_same = sw[sw["pg_dow"] == postgres_dow]
            avg_hist = sw_same["total_sales"].mean() if len(sw_same) > 0 else None

            row = {
                "dept_id": dept_id,
                "department_name": actual_row["department_name"],
                "segment_type": actual_row["segment_type"] or "unknown",
                "date": d,
                "is_weekend": is_weekend,
                "actual": actual,
                "raw": raw,
                "avg_hist_same_weekday": avg_hist,
            }

            for t in THRESHOLDS:
                if t is None or avg_hist is None:
                    pred = raw
                else:
                    lo = avg_hist * (1 - t)
                    hi = avg_hist * (1 + t)
                    pred = float(np.clip(raw, lo, hi))
                key = f"t_{t}" if t is not None else "t_off"
                row[key] = pred

            results.append(row)

    rdf = pd.DataFrame(results)
    print(f"Total predictions: {len(rdf):,}")

    def metrics(actual: pd.Series, pred: pd.Series) -> dict:
        err = pred - actual
        ape = np.abs(err) / actual
        return {
            "MAPE_%": float(ape.mean() * 100),
            "MedianAPE_%": float(ape.median() * 100),
            "MAE": float(np.abs(err).mean()),
            "Bias_%": float(err.mean() / actual.mean() * 100),
        }

    variants = [f"t_{t}" if t is not None else "t_off" for t in THRESHOLDS]

    print("\n" + "=" * 80)
    print("OVERALL — sweep threshold")
    print("=" * 80)
    summary = pd.DataFrame({v: metrics(rdf["actual"], rdf[v]) for v in variants}).T
    print(summary.round(2).to_string())

    print("\n" + "=" * 80)
    print("WEEKDAYS")
    print("=" * 80)
    sub = rdf[~rdf["is_weekend"]]
    print(pd.DataFrame({v: metrics(sub["actual"], sub[v]) for v in variants}).T.round(2).to_string())

    print("\n" + "=" * 80)
    print("WEEKENDS")
    print("=" * 80)
    sub = rdf[rdf["is_weekend"]]
    print(pd.DataFrame({v: metrics(sub["actual"], sub[v]) for v in variants}).T.round(2).to_string())

    print("\n" + "=" * 80)
    print("BY SCALE (avg daily sales bucket)")
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
        print(f"\n[{bucket}]  n={len(sub):,}")
        s = pd.DataFrame({v: metrics(sub["actual"], sub[v]) for v in variants}).T
        print(s[["MAPE_%", "MedianAPE_%", "Bias_%"]].round(2).to_string())

    best_overall = summary["MAPE_%"].idxmin()
    print("\n" + "=" * 80)
    print(f"BEST OVERALL: {best_overall} → MAPE {summary.loc[best_overall, 'MAPE_%']:.2f}%")
    print("=" * 80)


if __name__ == "__main__":
    main()
