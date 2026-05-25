"""SKU-level forecast endpoints: retrain, batch predict, top-N, comparison, CSV."""

import csv
import io
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from ...auth import ApiKey, get_api_key_or_bypass
from ...db import get_db
from ...agents.sku_forecaster_agent import get_sku_forecaster_agent
from ...schemas.sku_forecast import (
    SkuComparisonResponse,
    SkuForecastBatchResponse,
    SkuForecastItem,
    SkuForecastRangeResponse,
    SkuModelInfoResponse,
    SkuRetrainRequest,
    SkuRetrainResponse,
    SkuTopNItem,
    SkuTopNResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sku", tags=["forecast-sku"])


# ------------------------------------------------------------------
# Retrain
# ------------------------------------------------------------------

@router.post("/retrain", response_model=SkuRetrainResponse)
async def retrain_sku_model(
    request: Optional[SkuRetrainRequest] = None,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    try:
        req = request or SkuRetrainRequest()
        agent = get_sku_forecaster_agent()
        _, metrics = agent.train_model(
            db=db,
            days=req.days,
            active_window_days=req.active_window_days,
        )
        return SkuRetrainResponse(
            status="success",
            message="SKU model trained successfully",
            metrics=metrics,
            timestamp=datetime.utcnow().isoformat(),
            training_samples=metrics.get('train_samples', 0),
            n_features=metrics.get('n_features', 0),
            n_unique_skus=metrics.get('n_unique_skus', 0),
            n_unique_departments=metrics.get('n_unique_departments', 0),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"SKU retrain failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Model info
# ------------------------------------------------------------------

@router.get("/model/info", response_model=SkuModelInfoResponse)
async def get_sku_model_info(
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    agent = get_sku_forecaster_agent()
    info = agent.get_model_info()
    return SkuModelInfoResponse(**info)


# ------------------------------------------------------------------
# Batch forecast
# ------------------------------------------------------------------

@router.get("/batch")
async def get_sku_batch_forecasts(
    department_id: str,
    from_date: date,
    to_date: Optional[date] = None,
    top_n: int = 50,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    if to_date is None:
        to_date = from_date

    if (to_date - from_date).days > 30:
        raise HTTPException(status_code=400, detail="Max range is 30 days")

    agent = get_sku_forecaster_agent()
    if agent.model is None:
        raise HTTPException(status_code=400, detail="SKU model not trained yet — POST /forecast/sku/retrain first")

    dept_row = db.execute(
        text("SELECT name FROM departments WHERE id = :did"),
        {"did": department_id},
    ).fetchone()
    dept_name = dept_row[0] if dept_row else department_id

    daily_forecasts = []
    d = from_date
    while d <= to_date:
        items = agent.forecast_department_skus(department_id, d, db, top_n=top_n)
        fi = [SkuForecastItem(**it) for it in items]
        total_qty = sum(it.predicted_qty for it in fi)
        total_rev = sum(it.estimated_revenue or 0 for it in fi)
        daily_forecasts.append(SkuForecastBatchResponse(
            department_id=department_id,
            department_name=dept_name,
            forecast_date=str(d),
            items=fi,
            total_predicted_qty=round(total_qty, 1),
            total_estimated_revenue=round(total_rev, 2) if total_rev else None,
            model_version=agent._training_metrics.get('trained_at') if agent._training_metrics else None,
        ))
        d += timedelta(days=1)

    return SkuForecastRangeResponse(
        department_id=department_id,
        department_name=dept_name,
        from_date=str(from_date),
        to_date=str(to_date),
        daily_forecasts=daily_forecasts,
    )


# ------------------------------------------------------------------
# Top-N SKU
# ------------------------------------------------------------------

@router.get("/top-n", response_model=SkuTopNResponse)
async def get_top_n_skus(
    department_id: Optional[str] = None,
    period_days: int = 30,
    n: int = 50,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    cutoff = date.today() - timedelta(days=period_days)
    params: dict = {"cutoff": cutoff, "n": n}

    dept_filter = ""
    if department_id:
        dept_filter = "AND sds.department_id = :dept_id"
        params["dept_id"] = department_id

    rows = db.execute(text(f"""
        SELECT p.id, p.name, p.type, ng.name AS group_name,
               SUM(sds.total_sum) AS total_revenue,
               SUM(sds.total_qty) AS total_qty,
               ROUND(SUM(sds.total_qty) / GREATEST(COUNT(DISTINCT sds.sale_date), 1), 2) AS avg_daily_qty,
               ROW_NUMBER() OVER (ORDER BY SUM(sds.total_sum) DESC) AS rank
        FROM sku_daily_sales sds
        JOIN product p ON p.id = sds.product_id
        LEFT JOIN nomenclature_group ng ON ng.id = p.group_id
        WHERE sds.sale_date >= :cutoff {dept_filter}
        GROUP BY p.id, p.name, p.type, ng.name
        ORDER BY total_revenue DESC
        LIMIT :n
    """), params).fetchall()

    items = [
        SkuTopNItem(
            product_id=r[0], product_name=r[1], product_type=r[2],
            group_name=r[3],
            total_revenue=float(r[4] or 0), total_qty=float(r[5] or 0),
            avg_daily_qty=float(r[6] or 0), rank=int(r[7]),
        )
        for r in rows
    ]

    return SkuTopNResponse(
        department_id=department_id,
        period_days=period_days,
        items=items,
    )


# ------------------------------------------------------------------
# Comparison (predicted vs actual)
# ------------------------------------------------------------------

@router.get("/comparison")
async def get_sku_comparison(
    department_id: str,
    from_date: date,
    to_date: date,
    product_id: Optional[int] = None,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    params: dict = {"dept": department_id, "from": from_date, "to": to_date}
    product_filter = ""
    if product_id:
        product_filter = "AND sds.product_id = :pid"
        params["pid"] = product_id

    rows = db.execute(text(f"""
        SELECT sds.sale_date, sds.product_id, p.name AS product_name,
               sds.department_id, d.name AS department_name,
               sf.predicted_qty, sds.total_qty AS actual_qty
        FROM sku_daily_sales sds
        JOIN product p ON p.id = sds.product_id
        JOIN departments d ON d.id = sds.department_id
        LEFT JOIN sku_forecasts sf
            ON sf.department_id = sds.department_id
           AND sf.product_id = sds.product_id
           AND sf.forecast_date = sds.sale_date
        WHERE sds.department_id = :dept
          AND sds.sale_date >= :from AND sds.sale_date <= :to
          {product_filter}
        ORDER BY sds.sale_date, sds.total_qty DESC
    """), params).fetchall()

    items = []
    total_error = 0.0
    n_compared = 0
    for r in rows:
        pred = float(r[5]) if r[5] is not None else None
        actual = float(r[6])
        error = abs(pred - actual) if pred is not None else None
        error_pct = (error / actual * 100) if error is not None and actual > 0 else None
        if error is not None:
            total_error += error_pct or 0
            n_compared += 1
        items.append({
            'date': str(r[0]),
            'product_id': int(r[1]),
            'product_name': r[2],
            'department_id': str(r[3]),
            'department_name': r[4],
            'predicted_qty': round(pred, 1) if pred is not None else None,
            'actual_qty': round(actual, 1),
            'error': round(error, 2) if error is not None else None,
            'error_pct': round(error_pct, 1) if error_pct is not None else None,
        })

    return SkuComparisonResponse(
        items=items,
        summary={
            'total_items': len(items),
            'compared': n_compared,
            'avg_mape': round(total_error / n_compared, 2) if n_compared else None,
        },
    )


# ------------------------------------------------------------------
# CSV export
# ------------------------------------------------------------------

@router.get("/export/csv")
async def export_sku_forecasts_csv(
    department_id: str,
    from_date: date,
    to_date: Optional[date] = None,
    top_n: int = 50,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    if to_date is None:
        to_date = from_date

    agent = get_sku_forecaster_agent()
    if agent.model is None:
        raise HTTPException(status_code=400, detail="SKU model not trained")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'date', 'product_id', 'product_name', 'product_type',
        'group', 'category', 'predicted_qty', 'avg_price', 'estimated_revenue',
    ])

    d = from_date
    while d <= to_date:
        items = agent.forecast_department_skus(department_id, d, db, top_n=top_n)
        for it in items:
            writer.writerow([
                str(d), it['product_id'], it['product_name'], it['product_type'],
                it.get('group_name', ''), it.get('category_name', ''),
                it['predicted_qty'], it.get('avg_price', ''), it.get('estimated_revenue', ''),
            ])
        d += timedelta(days=1)

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=sku_forecast_{department_id}_{from_date}_{to_date}.csv"},
    )


# ------------------------------------------------------------------
# Backfill aggregation (admin utility)
# ------------------------------------------------------------------

@router.post("/aggregate/backfill")
async def backfill_sku_aggregation(
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    from ...services.sku_daily_aggregation_service import SkuDailyAggregationService
    result = SkuDailyAggregationService(db).backfill_all()
    return result
