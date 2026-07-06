"""CLI для like-for-like сравнения двух department-level моделей на hold-out.

Логика живёт в app/services/model_comparison.py (её же использует
deployment decision автопереобучения, Фаза 1.2). Скрипт — тонкая обёртка.

Запуск (внутри контейнера, читает прод-БД read-only):
    docker cp scripts/compare_models_holdout.py sales-forecast-app:/tmp/
    docker exec -w /app -e PYTHONPATH=/app sales-forecast-app \
        python /tmp/compare_models_holdout.py \
        --model-a models/lgbm_model.pkl \
        --model-b models/backup_lgbm_model_20260621_030006.pkl
"""

import argparse
import json
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-a", required=True)
    parser.add_argument("--model-b", required=True)
    parser.add_argument("--days", type=int, default=28)
    parser.add_argument("--json", help="Путь для JSON-результата (опционально)")
    args = parser.parse_args()

    from app.db import SessionLocal
    from app.services.model_comparison import compare_on_holdout

    db = SessionLocal()
    try:
        result = compare_on_holdout(db, args.model_a, args.model_b, holdout_days=args.days)
    finally:
        db.close()

    h = result["holdout"]
    print(f"\nHold-out: {h['from']} .. {h['to']} ({h['days']}д, {h['rows']} строк)")
    print(f"{'модель':<55} {'trained_at':<28} {'WAPE':>7} {'MedAPE':>7} {'MAPE':>7}")
    for key in ("a", "b"):
        r = result[key]
        print(f"{r['model_path']:<55} {str(r['trained_at']):<28} "
              f"{r['wape']:>6.2f}% {r['median_ape']:>6.2f}% {r['mape']:>6.2f}%")
        if r["missing_features_filled_0"]:
            print(f"    ⚠ отсутствующие фичи заполнены 0: {r['missing_features_filled_0']}")
    print(f"\nПобедитель по WAPE: {result['winner']}")

    if args.json:
        with open(args.json, "w") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    return 0


if __name__ == "__main__":
    sys.exit(main())
