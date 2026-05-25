"""Aggregate receipt_item rows into sku_daily_sales for ML training.

Called automatically after each receipts sync and on-demand via API.
"""

import logging
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

AGGREGATE_SQL = text("""
    INSERT INTO sku_daily_sales
        (department_id, product_id, sale_date, total_qty, total_sum, receipt_count, synced_at)
    SELECT
        r.department_id,
        ri.product_id,
        ri.open_date,
        SUM(ri.qty),
        SUM(ri.dish_sum),
        COUNT(DISTINCT ri.receipt_id),
        NOW()
    FROM receipt_item ri
    JOIN receipt r ON r.id = ri.receipt_id AND r.open_date = ri.open_date
    JOIN product p ON p.id = ri.product_id
    WHERE ri.open_date >= :from_date
      AND ri.open_date <= :to_date
      AND ri.product_id IS NOT NULL
      AND p.type IN ('DISH', 'GOODS')
    GROUP BY r.department_id, ri.product_id, ri.open_date
    ON CONFLICT (department_id, product_id, sale_date)
    DO UPDATE SET
        total_qty     = EXCLUDED.total_qty,
        total_sum     = EXCLUDED.total_sum,
        receipt_count = EXCLUDED.receipt_count,
        synced_at     = NOW()
""")


class SkuDailyAggregationService:
    def __init__(self, db: Session):
        self.db = db

    def aggregate_date_range(self, from_date: date, to_date: date) -> dict:
        """Aggregate receipt_item into sku_daily_sales for the given date range."""
        logger.info(f"SKU daily aggregation: {from_date} → {to_date}")
        result = self.db.execute(
            AGGREGATE_SQL,
            {"from_date": from_date, "to_date": to_date},
        )
        rows = result.rowcount
        self.db.commit()
        logger.info(f"SKU daily aggregation done: {rows} rows upserted")
        return {"rows_upserted": rows, "from_date": str(from_date), "to_date": str(to_date)}

    def backfill_all(self) -> dict:
        """Aggregate the full date range found in receipt_item."""
        row = self.db.execute(
            text("SELECT MIN(open_date), MAX(open_date) FROM receipt_item WHERE product_id IS NOT NULL")
        ).fetchone()
        if not row or not row[0]:
            logger.warning("No receipt_item data to aggregate")
            return {"rows_upserted": 0, "message": "no data"}
        return self.aggregate_date_range(row[0], row[1])
