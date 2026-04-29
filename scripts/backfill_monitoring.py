"""
Backfill forecasts + forecast_accuracy_log за последние 60 дней.

Симулирует, как если бы модель делала прогноз на каждый день в окне:
строит features из данных до D-1, применяет текущую пост-обработку
(smoothing threshold 0.3), сохраняет результат + сверяет с фактом.

Используется один раз для инициализации мониторинга. Дальше прогнозы
будут писаться при каждом /api/forecast/batch вызове.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import text

sys.path.insert(0, "/app")

from app.db import get_db
from app.models.branch import Department, SalesSummary
from app.agents.sales_forecaster_agent import SalesForecasterAgent


BACKFILL_DAYS = 60
MIN_HISTORY_DAYS = 14
SMOOTHING_THRESHOLD = 0.3  # production default after etap 1.2


def main() -> None:
    db = next(get_db())

    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=BACKFILL_DAYS - 1)
    history_start = start_date - timedelta(days=45)

    print(f"Backfill window: {start_date} .. {end_date}")

    agent = SalesForecasterAgent(model_path="/app/models/lgbm_model.pkl")
    if agent.model is None:
        print("ERROR: model not loaded")
        sys.exit(1)

    model_version = str(getattr(agent, "_trained_at", "unknown") or "unknown")
    print(f"Model version: {model_version}")

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

    backfill_dates = pd.date_range(start_date, end_date, freq="D").date

    forecasts_inserted = 0
    accuracy_inserted = 0
    skipped = 0

    upsert_forecast_sql = text("""
        INSERT INTO forecasts (branch_id, forecast_date, predicted_amount, model_version, created_at)
        VALUES (:bid, :fdate, :pred, :ver, :now)
        ON CONFLICT (branch_id, forecast_date) DO UPDATE
        SET predicted_amount = EXCLUDED.predicted_amount,
            model_version = EXCLUDED.model_version,
            created_at = EXCLUDED.created_at
    """)

    upsert_accuracy_sql = text("""
        INSERT INTO forecast_accuracy_log (branch_id, forecast_date, predicted_amount, actual_amount, mae, mape, created_at)
        VALUES (:bid, :fdate, :pred, :actual, :mae, :mape, :now)
        ON CONFLICT (branch_id, forecast_date) DO UPDATE
        SET predicted_amount = EXCLUDED.predicted_amount,
            actual_amount = EXCLUDED.actual_amount,
            mae = EXCLUDED.mae,
            mape = EXCLUDED.mape,
            created_at = EXCLUDED.created_at
    """)

    for dept_id, dept_df in df_all.groupby("department_id"):
        dept_df = dept_df.sort_values("date").reset_index(drop=True)
        dates_in_dept = set(dept_df["date"].dt.date.tolist())

        for d in backfill_dates:
            if d not in dates_in_dept:
                skipped += 1
                continue

            actual_row = dept_df[dept_df["date"].dt.date == d].iloc[0]
            actual = float(actual_row["total_sales"])
            if actual <= 0:
                skipped += 1
                continue

            hist_window_start = d - timedelta(days=31)
            hist_window_end = d - timedelta(days=1)
            hist = dept_df[
                (dept_df["date"].dt.date >= hist_window_start)
                & (dept_df["date"].dt.date <= hist_window_end)
            ]
            if len(hist) < MIN_HISTORY_DAYS:
                skipped += 1
                continue

            features = agent._create_prediction_features(d, hist.copy())
            X = pd.DataFrame([features])[agent.feature_columns]
            raw = max(0.0, float(agent.predict(X)[0]))

            python_dow = pd.Timestamp(d).dayofweek
            postgres_dow = (python_dow + 1) % 7

            sw_window_start = d - timedelta(days=28)
            sw = dept_df[
                (dept_df["date"].dt.date >= sw_window_start)
                & (dept_df["date"].dt.date <= hist_window_end)
            ].copy()
            sw["pg_dow"] = ((sw["date"].dt.dayofweek + 1) % 7).astype(int)
            sw_same = sw[sw["pg_dow"] == postgres_dow]

            if len(sw_same) > 0:
                avg_hist = sw_same["total_sales"].mean()
                lo = avg_hist * (1 - SMOOTHING_THRESHOLD)
                hi = avg_hist * (1 + SMOOTHING_THRESHOLD)
                pred = float(np.clip(raw, lo, hi))
            else:
                pred = raw

            now = datetime.utcnow()

            db.execute(upsert_forecast_sql, {
                "bid": str(dept_id), "fdate": d, "pred": pred,
                "ver": model_version, "now": now,
            })
            forecasts_inserted += 1

            mae = float(abs(pred - actual))
            mape = float(mae / actual * 100)

            db.execute(upsert_accuracy_sql, {
                "bid": str(dept_id), "fdate": d, "pred": float(pred),
                "actual": float(actual), "mae": mae, "mape": mape, "now": now,
            })
            accuracy_inserted += 1

        db.commit()

    print(f"\nForecasts upserted: {forecasts_inserted:,}")
    print(f"Accuracy log entries: {accuracy_inserted:,}")
    print(f"Skipped (no data / short history): {skipped:,}")

    avg_mape = db.execute(text("""
        SELECT AVG(mape)::numeric(8,2) AS avg_mape, COUNT(*) AS n,
               MIN(forecast_date) AS earliest, MAX(forecast_date) AS latest
        FROM forecast_accuracy_log
    """)).fetchone()

    print(f"\nMonitoring snapshot:")
    print(f"  avg MAPE: {avg_mape.avg_mape}%")
    print(f"  rows: {avg_mape.n}")
    print(f"  range: {avg_mape.earliest} .. {avg_mape.latest}")


if __name__ == "__main__":
    main()
