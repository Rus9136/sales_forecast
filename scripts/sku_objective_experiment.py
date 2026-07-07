"""Эксперимент: objective='tweedie' vs 'log1p' для SKU-модели (Фаза 2.5).

Оба варианта обучаются на ОДНИХ pre-holdout данных и оцениваются на ОДНОМ
hold-out (последние N дней), включая intermittent-разрез (нулевые/ненулевые
дни). Если tweedie не лучше log1p по WAPE — оставляем log1p (текущий).

Запуск:
    docker cp scripts/sku_objective_experiment.py sales-forecast-app:/tmp/
    docker exec -w /app -e PYTHONPATH=/app sales-forecast-app \
        python /tmp/sku_objective_experiment.py
"""

import sys
from datetime import date, timedelta

sys.path.insert(0, "/app")

HOLDOUT_DAYS = 21
TRAIN_DAYS = 90


def main():
    from app.agents.sku_forecaster_agent import SkuForecasterAgent
    from app.db import get_db
    from app.services.sku_model_comparison import evaluate_agent, load_holdout_world
    from app.services.sku_training_service import SkuTrainingDataService

    db = next(get_db())
    try:
        decision_end = date.today() - timedelta(days=1 + HOLDOUT_DAYS)
        svc = SkuTrainingDataService(db)
        df = svc.prepare_training_data(days=TRAIN_DAYS, end_date=decision_end)
        if df.empty:
            print("No training data")
            return 1
        train_df, val_df, test_df = svc.split_train_validation_test(df)
        feature_cols = svc.get_feature_columns()
        encoding_maps = svc.encoding_maps
        del df

        # общий hold-out для обоих
        grid, product_meta, dept_meta, holdout_start = load_holdout_world(db, HOLDOUT_DAYS)

        rows = []
        for objective in ("log1p", "tweedie"):
            agent = SkuForecasterAgent(model_path=f"/tmp/exp_sku_{objective}.pkl")
            agent.feature_columns = feature_cols
            agent._encoding_maps = encoding_maps
            agent._objective = objective
            _, m = agent.train_model(
                train_df.copy(), val_df.copy(), test_df.copy(), save_model=False,
            )
            hold = evaluate_agent(agent, grid, product_meta, dept_meta, holdout_start)
            rows.append({
                "objective": objective,
                "holdout_WAPE": hold["wape"],
                "holdout_MedAPE": hold["median_ape"],
                "holdout_nonzero_WAPE": hold["nonzero_wape"],
                "holdout_zero_mean_pred": hold["zero_day_mean_pred"],
                "test_WAPE": round(m["test_wape"], 2),
                "test_zero_share": round(m["test_zero_day_share"], 3),
                "test_nonzero_WAPE": round(m["test_nonzero_wape"], 2),
            })

        print("\n" + "=" * 80)
        print("SKU OBJECTIVE EXPERIMENT — tweedie vs log1p (общий hold-out)")
        print("=" * 80)
        import pandas as pd
        res = pd.DataFrame(rows)
        print(res.to_string(index=False))

        log1p_w = res[res.objective == "log1p"]["holdout_WAPE"].iloc[0]
        tweedie_w = res[res.objective == "tweedie"]["holdout_WAPE"].iloc[0]
        print("\nВЫВОД:", end=" ")
        if tweedie_w < log1p_w - 0.5:
            print(f"tweedie ЛУЧШЕ на hold-out ({tweedie_w:.2f}% vs {log1p_w:.2f}% WAPE) — рекомендуется переключить objective")
        else:
            print(f"tweedie НЕ лучше ({tweedie_w:.2f}% vs {log1p_w:.2f}% WAPE) — оставляем log1p")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
