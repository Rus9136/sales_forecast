"""
Honest 30-day forecast backtest.

Производственный сценарий: в конце месяца строится прогноз на следующие 30 дней
для построения графика смен официантов. Все lag-/rolling-фичи на горизонте >1
дня уходят в "будущее" — приходится использовать рекурсивные предсказания.

Текущая 1-day-ahead метрика (raw MAPE 36%) — лучший случай. Этот скрипт меряет
честную деградацию по горизонтам h=1, 7, 14, 30.

Запуск:
    docker cp scripts/backtest_30day.py sales-forecast-app:/app/backtest_30day.py
    docker exec sales-forecast-app python /app/backtest_30day.py
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


# Anchor dates — первое число месяца, на которое строим 30-day прогноз.
# Используем последние 2-3 месяца истории. Берём первые числа месяцев,
# для которых есть полные 30 дней факта вперёд и >= 60 дней истории назад.
ANCHOR_DATES = [
    date(2026, 3, 1),   # forecast Mar 1..Mar 30, history through Feb 28
    date(2026, 4, 1),   # forecast Apr 1..Apr 30, history through Mar 31
]

HORIZON_DAYS = 30
HISTORY_DAYS = 60  # минимум истории до anchor для lag/rolling
MIN_HISTORY_FOR_FORECAST = 14
HORIZON_BUCKETS = [(1, 1), (2, 7), (8, 14), (15, 21), (22, 30)]


def main() -> None:
    db = next(get_db())

    agent = SalesForecasterAgent(model_path="/app/models/lgbm_model.pkl")
    if agent.model is None:
        print("ERROR: model not loaded")
        sys.exit(1)
    print(f"Model loaded. Feature count: {len(agent.feature_columns)}")
    print(f"Anchor dates: {ANCHOR_DATES}")
    print(f"Horizon: {HORIZON_DAYS} days each\n")

    # Загружаем все sales за нужный диапазон одним запросом
    earliest_history = min(ANCHOR_DATES) - timedelta(days=HISTORY_DAYS + 5)
    latest_actual = max(ANCHOR_DATES) + timedelta(days=HORIZON_DAYS - 1)

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
            Department.brand.label("brand"),
            Department.location_type.label("location_type"),
            Department.tourist_traffic_dependent.label("tourist_traffic_dependent"),
            Department.is_24_7.label("is_24_7_flag"),
            Department.opening_hour.label("opening_hour"),
            Department.closing_hour.label("closing_hour"),
            Department.seasonality_intensity.label("seasonality_intensity"),
            Department.opened_date.label("opened_date"),
            Department.season_start_month.label("season_start_month"),
            Department.season_end_month.label("season_end_month"),
        )
        .join(Department, SalesSummary.department_id == Department.id)
        .filter(SalesSummary.date >= earliest_history)
        .filter(SalesSummary.date <= latest_actual)
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
                "brand": r.brand,
                "location_type": r.location_type,
                "tourist_traffic_dependent": bool(r.tourist_traffic_dependent),
                "is_24_7_flag": bool(r.is_24_7_flag),
                "opening_hour": r.opening_hour,
                "closing_hour": r.closing_hour,
                "seasonality_intensity": r.seasonality_intensity or 'none',
                "opened_date": r.opened_date,
                "season_start_month": r.season_start_month,
                "season_end_month": r.season_end_month,
            }
            for r in rows
        ]
    )
    df_all["date"] = pd.to_datetime(df_all["date"])
    df_all = df_all.sort_values(["department_id", "date"]).reset_index(drop=True)
    print(f"Loaded {len(df_all):,} sales rows for {df_all['department_id'].nunique()} departments\n")

    results: list[dict] = []

    for anchor in ANCHOR_DATES:
        history_cutoff = anchor - timedelta(days=1)  # last real day available
        history_start = anchor - timedelta(days=HISTORY_DAYS)

        for dept_id, dept_df in df_all.groupby("department_id"):
            dept_df = dept_df.sort_values("date").reset_index(drop=True)

            real_history = dept_df[
                (dept_df["date"].dt.date >= history_start)
                & (dept_df["date"].dt.date <= history_cutoff)
            ].copy()

            if len(real_history) < MIN_HISTORY_FOR_FORECAST:
                continue

            # Скользящая история: содержит реальные продажи до anchor-1,
            # дальше дозаполняется предсказаниями для рекурсивного h-step
            running_history = real_history.copy()

            for h in range(1, HORIZON_DAYS + 1):
                forecast_date = anchor + timedelta(days=h - 1)

                # Реальный факт (для метрик)
                actual_row = dept_df[dept_df["date"].dt.date == forecast_date]
                if actual_row.empty or actual_row.iloc[0]["total_sales"] <= 0:
                    # пропуск дней без факта (или ноль) — нечего сравнивать
                    # но всё равно генерируем предсказание для рекурсии
                    pass

                features = agent._create_prediction_features(forecast_date, running_history)
                X = pd.DataFrame([features])[agent.feature_columns]
                pred = max(0.0, float(agent.predict(X, segment_type=actual_row.iloc[0]["segment_type"]
                                                   if not actual_row.empty else None)[0]))

                # Добавляем предсказание в running_history как "будущий факт"
                # для следующего horizon step (recursive). Метаданные подразделения
                # копируем из последней реальной строки.
                last_meta = real_history.iloc[-1]
                running_history = pd.concat(
                    [running_history,
                     pd.DataFrame([{
                         "date": pd.Timestamp(forecast_date),
                         "total_sales": pred,
                         "department_name": last_meta["department_name"],
                         "department_code": last_meta["department_code"],
                         "department_type": last_meta["department_type"],
                         "segment_type": last_meta["segment_type"],
                         "parent_id": last_meta["parent_id"],
                         "department_id": dept_id,
                         "brand": last_meta.get("brand"),
                         "location_type": last_meta.get("location_type"),
                         "tourist_traffic_dependent": last_meta.get("tourist_traffic_dependent", False),
                         "is_24_7_flag": last_meta.get("is_24_7_flag", False),
                         "opening_hour": last_meta.get("opening_hour"),
                         "closing_hour": last_meta.get("closing_hour"),
                         "seasonality_intensity": last_meta.get("seasonality_intensity", "none"),
                         "opened_date": last_meta.get("opened_date"),
                         "season_start_month": last_meta.get("season_start_month"),
                         "season_end_month": last_meta.get("season_end_month"),
                     }])],
                    ignore_index=True,
                )

                # Если факт есть — записываем в результаты
                if not actual_row.empty and actual_row.iloc[0]["total_sales"] > 0:
                    actual = float(actual_row.iloc[0]["total_sales"])
                    results.append({
                        "anchor": anchor,
                        "dept_id": dept_id,
                        "department_name": real_history.iloc[-1]["department_name"],
                        "segment_type": real_history.iloc[-1]["segment_type"] or "unknown",
                        "date": forecast_date,
                        "horizon": h,
                        "actual": actual,
                        "predicted": pred,
                    })

    rdf = pd.DataFrame(results)
    print(f"Total (anchor, dept, horizon) predictions with actual: {len(rdf):,}")
    if rdf.empty:
        print("No predictions generated.")
        return

    rdf["err"] = rdf["predicted"] - rdf["actual"]
    rdf["ape"] = (rdf["err"].abs() / rdf["actual"]).clip(upper=10)

    out_path = "/tmp/backtest_30day_results.csv"
    rdf.to_csv(out_path, index=False)
    print(f"Raw results saved to {out_path}\n")

    def metrics(g: pd.DataFrame) -> dict:
        return {
            "n": len(g),
            "MAPE_%": round(g["ape"].mean() * 100, 2),
            "MedianAPE_%": round(g["ape"].median() * 100, 2),
            "MAE": round(g["err"].abs().mean()),
            "Bias_%": round((g["err"].mean() / g["actual"].mean()) * 100, 2),
        }

    # ---- by horizon (single day) ----
    print("=" * 90)
    print("MAPE / MedianAPE BY EXACT HORIZON (h=1..30)")
    print("=" * 90)
    hr = pd.DataFrame({h: metrics(rdf[rdf["horizon"] == h]) for h in range(1, HORIZON_DAYS + 1)}).T
    hr.index.name = "h_day"
    print(hr.to_string())

    # ---- by horizon bucket ----
    print("\n" + "=" * 90)
    print("MAPE / MedianAPE BY HORIZON BUCKET")
    print("=" * 90)
    rows = []
    for lo, hi in HORIZON_BUCKETS:
        sub = rdf[(rdf["horizon"] >= lo) & (rdf["horizon"] <= hi)]
        m = metrics(sub)
        m["bucket"] = f"h{lo}-{hi}"
        rows.append(m)
    print(pd.DataFrame(rows)[["bucket", "n", "MAPE_%", "MedianAPE_%", "MAE", "Bias_%"]].to_string(index=False))

    # ---- by anchor month ----
    print("\n" + "=" * 90)
    print("MAPE / MedianAPE BY ANCHOR MONTH (combined all horizons)")
    print("=" * 90)
    rows = []
    for anchor in ANCHOR_DATES:
        sub = rdf[rdf["anchor"] == anchor]
        if sub.empty:
            continue
        m = metrics(sub)
        m["anchor"] = str(anchor)
        rows.append(m)
    print(pd.DataFrame(rows)[["anchor", "n", "MAPE_%", "MedianAPE_%", "MAE", "Bias_%"]].to_string(index=False))

    # ---- segments × bucket ----
    print("\n" + "=" * 90)
    print("MAPE % BY SEGMENT × HORIZON BUCKET")
    print("=" * 90)
    seg_x_bucket: list[dict] = []
    for seg in sorted(rdf["segment_type"].unique()):
        for lo, hi in HORIZON_BUCKETS:
            sub = rdf[(rdf["segment_type"] == seg) &
                      (rdf["horizon"] >= lo) & (rdf["horizon"] <= hi)]
            if len(sub) < 30:
                continue
            seg_x_bucket.append({
                "segment": seg, "bucket": f"h{lo}-{hi}", "n": len(sub),
                "MAPE_%": round(sub["ape"].mean() * 100, 2),
                "MedianAPE_%": round(sub["ape"].median() * 100, 2),
            })
    print(pd.DataFrame(seg_x_bucket).to_string(index=False))

    # ---- size buckets × horizon bucket ----
    print("\n" + "=" * 90)
    print("MAPE % BY SCALE × HORIZON BUCKET (Q1-Q4 by avg dept sales)")
    print("=" * 90)
    dept_avg = rdf.groupby("dept_id")["actual"].mean()
    rdf["dept_avg"] = rdf["dept_id"].map(dept_avg)
    rdf["scale_bucket"] = pd.qcut(rdf["dept_avg"], q=4,
                                  labels=["Q1_smallest", "Q2", "Q3", "Q4_largest"])
    rows = []
    for q in ["Q1_smallest", "Q2", "Q3", "Q4_largest"]:
        for lo, hi in HORIZON_BUCKETS:
            sub = rdf[(rdf["scale_bucket"] == q) &
                      (rdf["horizon"] >= lo) & (rdf["horizon"] <= hi)]
            if len(sub) < 30:
                continue
            rows.append({
                "scale": q, "bucket": f"h{lo}-{hi}", "n": len(sub),
                "MAPE_%": round(sub["ape"].mean() * 100, 2),
                "MedianAPE_%": round(sub["ape"].median() * 100, 2),
            })
    print(pd.DataFrame(rows).to_string(index=False))

    # ---- monthly aggregate (sum of 30 days) ----
    print("\n" + "=" * 90)
    print("MONTHLY AGGREGATE ERROR (sum of 30-day forecast vs sum of actual, per dept)")
    print("=" * 90)
    monthly = (rdf.groupby(["anchor", "dept_id", "department_name"])
               .agg(sum_actual=("actual", "sum"),
                    sum_pred=("predicted", "sum"))
               .reset_index())
    monthly["err"] = monthly["sum_pred"] - monthly["sum_actual"]
    monthly["ape"] = (monthly["err"].abs() / monthly["sum_actual"]).clip(upper=10)
    monthly_metrics = {
        "n_dept_months": len(monthly),
        "MAPE_%_monthly_total": round(monthly["ape"].mean() * 100, 2),
        "MedianAPE_%_monthly_total": round(monthly["ape"].median() * 100, 2),
        "Bias_%": round(monthly["err"].sum() / monthly["sum_actual"].sum() * 100, 2),
    }
    print(monthly_metrics)
    print("\nKey insight: для планирования ФОТ важна именно эта метрика — суммарная "
          "выручка за 30 дней. Точность отдельного дня менее критична — важна"
          " общая нагрузка на штат за месяц.")


if __name__ == "__main__":
    main()
