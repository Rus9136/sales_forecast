"""Aggregate analytical views for pricing: price history, SKU weekly, department weekly.

Called daily by APScheduler (04:30) and on-demand via API backfill endpoint.
Follows the same pattern as sku_daily_aggregation_service.py.
"""

import logging
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Phase A: update last_seen_date for ongoing price periods
# Phase B: insert new price-change events via CTE with LAG
# ---------------------------------------------------------------------------

PRICE_HISTORY_UPDATE_SQL = text("""
    WITH daily_prices AS (
        SELECT department_id, product_id, sale_date,
               ROUND(total_sum / NULLIF(total_qty, 0), 2) AS avg_price
        FROM sku_daily_sales
        WHERE sale_date >= :from_date AND sale_date <= :to_date
          AND total_qty > 0
    ),
    latest_match AS (
        -- MAX(sale_date): UPDATE ... FROM с несколькими подходящими строками
        -- недетерминирован — last_seen_date мог встать не на максимальную дату
        SELECT product_id, department_id, avg_price, MAX(sale_date) AS max_seen
        FROM daily_prices
        GROUP BY product_id, department_id, avg_price
    )
    UPDATE sku_price_history sph
    SET last_seen_date = lm.max_seen
    FROM latest_match lm
    WHERE sph.product_id = lm.product_id
      AND sph.department_id = lm.department_id
      AND sph.price = lm.avg_price
      AND lm.max_seen > sph.last_seen_date
      -- БЕЗ окна давности: условие "last_seen >= sale_date - 7 days" навсегда
      -- «замораживало» период после паузы в продажах >7 дней (сезонные и
      -- редкие позиции при неизменной цене выглядели завершёнными)
      AND NOT EXISTS (
          SELECT 1 FROM sku_price_history newer
          WHERE newer.product_id = sph.product_id
            AND newer.department_id = sph.department_id
            AND newer.first_seen_date > sph.first_seen_date
      )
""")

PRICE_HISTORY_INSERT_SQL = text("""
    WITH daily_prices AS (
        SELECT department_id, product_id, sale_date,
               ROUND(total_sum / NULLIF(total_qty, 0), 2) AS avg_price
        FROM sku_daily_sales
        WHERE sale_date >= :context_date AND sale_date <= :to_date
          AND total_qty > 0
    ),
    with_prev AS (
        SELECT
            dp.department_id, dp.product_id, dp.sale_date, dp.avg_price,
            LAG(dp.avg_price) OVER (
                PARTITION BY dp.product_id, dp.department_id
                ORDER BY dp.sale_date
            ) AS lag_price
        FROM daily_prices dp
    ),
    with_history AS (
        SELECT
            wp.*,
            COALESCE(wp.lag_price, latest.price) AS prev_price_resolved
        FROM with_prev wp
        LEFT JOIN LATERAL (
            SELECT price FROM sku_price_history h
            WHERE h.product_id = wp.product_id
              AND h.department_id = wp.department_id
            ORDER BY h.first_seen_date DESC
            LIMIT 1
        ) latest ON wp.lag_price IS NULL
    ),
    changes AS (
        SELECT
            product_id, department_id,
            avg_price AS price,
            prev_price_resolved AS prev_price,
            CASE WHEN prev_price_resolved > 0
                 THEN ROUND((avg_price - prev_price_resolved) / prev_price_resolved, 4)
            END AS change_pct,
            sale_date AS first_seen_date,
            sale_date AS last_seen_date
        FROM with_history
        WHERE sale_date >= :from_date
          AND (prev_price_resolved IS NULL OR avg_price <> prev_price_resolved)
    )
    INSERT INTO sku_price_history
        (product_id, department_id, price, prev_price, change_pct,
         first_seen_date, last_seen_date)
    SELECT product_id, department_id, price, prev_price, change_pct,
           first_seen_date, last_seen_date
    FROM changes
    ON CONFLICT (product_id, department_id, first_seen_date)
    DO UPDATE SET
        last_seen_date = GREATEST(sku_price_history.last_seen_date, EXCLUDED.last_seen_date),
        price          = EXCLUDED.price,
        prev_price     = EXCLUDED.prev_price,
        change_pct     = EXCLUDED.change_pct
""")

# ---------------------------------------------------------------------------
# SKU weekly summary
# ---------------------------------------------------------------------------

SKU_WEEKLY_SQL = text("""
    WITH week_costs AS (
        SELECT
            ri.product_id,
            r.department_id,
            date_trunc('week', ri.open_date)::date AS week_start,
            -- cost_price из iiko (ProductCostBase.ProductCost) — себестоимость ВСЕЙ строки
            -- чека целиком (за все qty), а не за единицу. Умножать на qty нельзя — двойной учёт.
            SUM(COALESCE(ri.cost_price, 0)) AS total_cost,
            ROUND(
                SUM(CASE WHEN ri.cost_price IS NOT NULL THEN 1 ELSE 0 END)::numeric
                / GREATEST(COUNT(*)::numeric, 1), 4
            ) AS cost_coverage
        FROM receipt_item ri
        JOIN receipt r ON r.id = ri.receipt_id AND r.open_date = ri.open_date
        WHERE ri.open_date >= :from_date AND ri.open_date <= :to_date
          AND ri.product_id IS NOT NULL
        GROUP BY ri.product_id, r.department_id, date_trunc('week', ri.open_date)::date
    )
    INSERT INTO sku_weekly_summary
        (product_id, department_id, week_start, total_qty, total_revenue,
         total_cost, gross_profit, gp_margin, avg_price, avg_daily_qty,
         unique_receipts, days_with_sales, qty_cv, cost_coverage, synced_at)
    SELECT
        sds.product_id,
        sds.department_id,
        date_trunc('week', sds.sale_date)::date AS week_start,
        SUM(sds.total_qty),
        SUM(sds.total_sum),
        COALESCE(wc.total_cost, 0),
        SUM(sds.total_sum) - COALESCE(wc.total_cost, 0),
        CASE WHEN SUM(sds.total_sum) > 0
             THEN LEAST(GREATEST(ROUND(
                 (SUM(sds.total_sum) - COALESCE(wc.total_cost, 0)) / SUM(sds.total_sum), 4
             ), -9.9999), 9.9999)
        END,
        CASE WHEN SUM(sds.total_qty) > 0
             THEN ROUND(SUM(sds.total_sum) / SUM(sds.total_qty), 2)
        END,
        ROUND(SUM(sds.total_qty) / GREATEST(COUNT(*)::numeric, 1), 3),
        SUM(sds.receipt_count),
        COUNT(*)::integer,
        CASE WHEN AVG(sds.total_qty) > 0
             THEN LEAST(ROUND(
                 COALESCE(STDDEV_SAMP(sds.total_qty), 0) / AVG(sds.total_qty), 4
             ), 9.9999)
        END,
        COALESCE(wc.cost_coverage, 0),
        NOW()
    FROM sku_daily_sales sds
    LEFT JOIN week_costs wc
        ON wc.product_id = sds.product_id
       AND wc.department_id = sds.department_id
       AND wc.week_start = date_trunc('week', sds.sale_date)::date
    WHERE sds.sale_date >= :from_date AND sds.sale_date <= :to_date
    GROUP BY sds.product_id, sds.department_id,
             date_trunc('week', sds.sale_date)::date,
             wc.total_cost, wc.cost_coverage
    ON CONFLICT (product_id, department_id, week_start)
    DO UPDATE SET
        total_qty       = EXCLUDED.total_qty,
        total_revenue   = EXCLUDED.total_revenue,
        total_cost      = EXCLUDED.total_cost,
        gross_profit    = EXCLUDED.gross_profit,
        gp_margin       = EXCLUDED.gp_margin,
        avg_price       = EXCLUDED.avg_price,
        avg_daily_qty   = EXCLUDED.avg_daily_qty,
        unique_receipts = EXCLUDED.unique_receipts,
        days_with_sales = EXCLUDED.days_with_sales,
        qty_cv          = EXCLUDED.qty_cv,
        cost_coverage   = EXCLUDED.cost_coverage,
        synced_at       = NOW()
""")

# ---------------------------------------------------------------------------
# Department weekly summary
# ---------------------------------------------------------------------------

DEPT_WEEKLY_SQL = text("""
    WITH dept_costs AS (
        SELECT
            r.department_id,
            date_trunc('week', ri.open_date)::date AS week_start,
            -- cost_price из iiko (ProductCostBase.ProductCost) — себестоимость ВСЕЙ строки
            -- чека целиком (за все qty), а не за единицу. Умножать на qty нельзя — двойной учёт.
            SUM(COALESCE(ri.cost_price, 0)) AS total_cost,
            ROUND(
                SUM(CASE WHEN ri.cost_price IS NOT NULL THEN 1 ELSE 0 END)::numeric
                / GREATEST(COUNT(*)::numeric, 1), 4
            ) AS cost_coverage
        FROM receipt_item ri
        JOIN receipt r ON r.id = ri.receipt_id AND r.open_date = ri.open_date
        WHERE ri.open_date >= :from_date AND ri.open_date <= :to_date
        GROUP BY r.department_id, date_trunc('week', ri.open_date)::date
    )
    INSERT INTO department_weekly_summary
        (department_id, week_start, total_revenue, total_cost, gross_profit,
         gp_margin, total_receipts, avg_receipt_sum, unique_guests,
         cost_coverage, synced_at)
    SELECT
        r.department_id,
        date_trunc('week', r.open_date)::date AS week_start,
        SUM(r.total_sum),
        COALESCE(dc.total_cost, 0),
        SUM(r.total_sum) - COALESCE(dc.total_cost, 0),
        CASE WHEN SUM(r.total_sum) > 0
             THEN LEAST(GREATEST(ROUND(
                 (SUM(r.total_sum) - COALESCE(dc.total_cost, 0)) / SUM(r.total_sum), 4
             ), -9.9999), 9.9999)
        END,
        COUNT(*)::integer,
        CASE WHEN COUNT(*) > 0
             THEN ROUND(SUM(r.total_sum) / COUNT(*)::numeric, 2)
        END,
        COALESCE(SUM(r.guest_num), 0)::integer,
        COALESCE(dc.cost_coverage, 0),
        NOW()
    FROM receipt r
    LEFT JOIN dept_costs dc
        ON dc.department_id = r.department_id
       AND dc.week_start = date_trunc('week', r.open_date)::date
    WHERE r.open_date >= :from_date AND r.open_date <= :to_date
    GROUP BY r.department_id, date_trunc('week', r.open_date)::date,
             dc.total_cost, dc.cost_coverage
    ON CONFLICT (department_id, week_start)
    DO UPDATE SET
        total_revenue   = EXCLUDED.total_revenue,
        total_cost      = EXCLUDED.total_cost,
        gross_profit    = EXCLUDED.gross_profit,
        gp_margin       = EXCLUDED.gp_margin,
        total_receipts  = EXCLUDED.total_receipts,
        avg_receipt_sum = EXCLUDED.avg_receipt_sum,
        unique_guests   = EXCLUDED.unique_guests,
        cost_coverage   = EXCLUDED.cost_coverage,
        synced_at       = NOW()
""")


class PricingAnalyticsService:
    def __init__(self, db: Session):
        self.db = db

    def aggregate_price_history(self, from_date: date, to_date: date) -> dict:
        """Detect price changes in sku_daily_sales and upsert into sku_price_history."""
        logger.info("Price history aggregation: %s → %s", from_date, to_date)

        # Phase A: extend last_seen_date for ongoing price periods
        res_a = self.db.execute(
            PRICE_HISTORY_UPDATE_SQL,
            {"from_date": from_date, "to_date": to_date},
        )
        updated = res_a.rowcount

        # Phase B: insert new price-change events (query from_date-1 for LAG context)
        context_date = from_date - timedelta(days=1)
        res_b = self.db.execute(
            PRICE_HISTORY_INSERT_SQL,
            {"context_date": context_date, "from_date": from_date, "to_date": to_date},
        )
        inserted = res_b.rowcount
        self.db.commit()

        logger.info("Price history done: %d updated, %d inserted", updated, inserted)
        return {"updated": updated, "inserted": inserted}

    def aggregate_sku_weekly(self, from_date: date, to_date: date) -> dict:
        """Aggregate sku_daily_sales + receipt_item costs into sku_weekly_summary.

        from_date принудительно расширяется до понедельника: вызов с середины
        недели пересчитывал строку недели по половине дней и перетирал
        корректные значения.
        """
        from_date = from_date - timedelta(days=from_date.weekday())
        logger.info("SKU weekly aggregation: %s → %s", from_date, to_date)
        result = self.db.execute(
            SKU_WEEKLY_SQL,
            {"from_date": from_date, "to_date": to_date},
        )
        rows = result.rowcount
        self.db.commit()
        logger.info("SKU weekly done: %d rows upserted", rows)
        return {"rows_upserted": rows}

    def aggregate_department_weekly(self, from_date: date, to_date: date) -> dict:
        """Aggregate receipt + receipt_item into department_weekly_summary.
        from_date выравнивается на понедельник (см. aggregate_sku_weekly)."""
        from_date = from_date - timedelta(days=from_date.weekday())
        logger.info("Department weekly aggregation: %s → %s", from_date, to_date)
        result = self.db.execute(
            DEPT_WEEKLY_SQL,
            {"from_date": from_date, "to_date": to_date},
        )
        rows = result.rowcount
        self.db.commit()
        logger.info("Department weekly done: %d rows upserted", rows)
        return {"rows_upserted": rows}

    def aggregate_all(self, from_date: date, to_date: date) -> dict:
        """Run all three aggregations."""
        r1 = self.aggregate_price_history(from_date, to_date)
        r2 = self.aggregate_sku_weekly(from_date, to_date)
        r3 = self.aggregate_department_weekly(from_date, to_date)
        return {"price_history": r1, "sku_weekly": r2, "department_weekly": r3}

    def backfill_all(self) -> dict:
        """Aggregate the full date range from sku_daily_sales."""
        row = self.db.execute(
            text("SELECT MIN(sale_date), MAX(sale_date) FROM sku_daily_sales")
        ).fetchone()
        if not row or not row[0]:
            logger.warning("No sku_daily_sales data to aggregate")
            return {"status": "no_data"}
        return self.aggregate_all(row[0], row[1])
