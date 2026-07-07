"""Core forecasting endpoints: retrain, model info, comparison, batch, CSV export."""

from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, or_
from datetime import date, datetime, timedelta
from typing import Optional, List
from pydantic import BaseModel
import logging
import traceback
import csv
import io

from ...db import get_db
from ...agents.sales_forecaster_agent import get_forecaster_agent
from ...models.branch import Department, SalesSummary
from ...auth import get_api_key_or_bypass, ApiKey, log_api_usage
from ..department import INACTIVE_THRESHOLD_DAYS

logger = logging.getLogger(__name__)

router = APIRouter()


class RetrainRequest(BaseModel):
    # Единая политика выбросов (аудит P1-2): flag-only по умолчанию — как
    # auto-retrain и как документированный no-body /retrain. Winsorize клиппит
    # и test-таргет (завышая метрики) — доступен только явным запросом для
    # ablation. is_outlier_day-флаг добавляется всегда, таргет не портится.
    handle_outliers: Optional[bool] = False
    outlier_method: Optional[str] = 'flag'
    days: Optional[int] = None


@router.post("/retrain")
async def retrain_model(
    request: Optional[RetrainRequest] = None,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Retrain the sales forecasting model with latest data."""
    try:
        from ...services.training_service import TrainingDataService

        training_service = TrainingDataService(db)
        logger.info("Starting model retraining...")

        kwargs = {}
        if request:
            if request.handle_outliers is not None:
                kwargs['handle_outliers'] = request.handle_outliers
            if request.outlier_method:
                kwargs['outlier_method'] = request.outlier_method
            if request.days:
                kwargs['days'] = request.days

        training_data = training_service.prepare_training_data(**kwargs)

        if training_data.empty:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No training data available"
            )

        logger.info(f"Training data prepared: {len(training_data)} samples")

        forecaster = get_forecaster_agent()
        train_df, val_df, test_df = training_service.split_train_validation_test(training_data)
        model, results = forecaster.train_model(train_df, val_df, test_df)

        logger.info(f"Model training completed. Metrics: {results}")

        return {
            "status": "success",
            "message": "Model retrained successfully",
            "metrics": results,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retraining model: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retraining model: {str(e)}"
        )


@router.post("/retrain-segmented")
async def retrain_segmented_models(
    request: Optional[RetrainRequest] = None,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Retrain per-segment models (one LGBM per segment_type).

    Trains alongside the global model — global stays as a fallback for
    departments whose segment has too few samples or an unknown segment_type.
    """
    try:
        from ...services.training_service import TrainingDataService

        training_service = TrainingDataService(db)
        logger.info("Starting per-segment model retraining...")

        kwargs = {}
        if request:
            if request.handle_outliers is not None:
                kwargs['handle_outliers'] = request.handle_outliers
            if request.outlier_method:
                kwargs['outlier_method'] = request.outlier_method
            if request.days:
                kwargs['days'] = request.days

        training_data = training_service.prepare_training_data(**kwargs)
        if training_data.empty:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No training data available"
            )

        forecaster = get_forecaster_agent()
        forecaster.feature_columns = training_service.get_feature_columns()
        per_segment_metrics = forecaster.train_segmented_models(training_data)

        return {
            "status": "success",
            "message": f"Trained {len(per_segment_metrics)} per-segment models",
            "per_segment_metrics": per_segment_metrics,
            "timestamp": datetime.now().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retraining segmented models: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retraining segmented models: {str(e)}"
        )


@router.get("/model/info")
async def get_model_info(
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Get information about the current model."""
    try:
        forecaster = get_forecaster_agent()
        return forecaster.get_model_info()
    except Exception as e:
        logger.error(f"Error getting model info: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting model info: {str(e)}"
        )


@router.get("/comparison")
async def get_forecast_comparison(
    from_date: date,
    to_date: date,
    department_id: Optional[str] = None,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Compare forecasts with actual sales."""
    try:
        if api_key:
            log_api_usage(api_key, "/forecast/comparison", db=db)

        sales_query = db.query(SalesSummary).filter(
            and_(SalesSummary.date >= from_date, SalesSummary.date <= to_date)
        )
        if department_id:
            sales_query = sales_query.filter(SalesSummary.department_id == department_id)
        else:
            # Скрываем мёртвые точки: department без продаж за последние N дней (от текущей даты).
            threshold_date = date.today() - timedelta(days=INACTIVE_THRESHOLD_DAYS)
            active_subq = (
                db.query(SalesSummary.department_id)
                .filter(SalesSummary.date >= threshold_date)
                .distinct()
                .subquery()
            )
            sales_query = sales_query.filter(SalesSummary.department_id.in_(active_subq))

        sales_data = sales_query.all()
        forecaster = get_forecaster_agent()

        results = []
        for sale in sales_data:
            department = db.query(Department).filter(Department.id == sale.department_id).first()

            try:
                prediction = forecaster.forecast(str(sale.department_id), sale.date, db)
            except Exception as pred_error:
                logger.warning(f"Failed to get prediction for {sale.date}, {sale.department_id}: {pred_error}")
                prediction = None

            error = None
            error_percentage = None
            if prediction and sale.total_sales:
                error = prediction - sale.total_sales
                error_percentage = (abs(error) / sale.total_sales) * 100

            results.append({
                "date": sale.date.isoformat(),
                "department_id": str(sale.department_id),
                "department_name": department.name if department else "Unknown",
                "predicted_sales": round(prediction, 2) if prediction else None,
                "actual_sales": sale.total_sales,
                "error": round(error, 2) if error else None,
                "error_percentage": round(error_percentage, 2) if error_percentage else None
            })

        return results

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting forecast comparison: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting forecast comparison: {str(e)}"
        )


@router.get("/batch")
async def get_batch_forecasts(
    from_date: date,
    to_date: date,
    department_id: Optional[str] = None,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Get batch forecasts for a date range."""
    try:
        if api_key:
            log_api_usage(api_key, "/forecast/batch", db=db)

        departments_query = db.query(Department)
        if department_id:
            departments_query = departments_query.filter(Department.id == department_id)
        else:
            # Скрываем мёртвые точки: DEPARTMENT без продаж за последние N дней.
            # Если department_id явно задан — пропускаем фильтр (вдруг хотят посмотреть архивную точку).
            threshold_date = date.today() - timedelta(days=INACTIVE_THRESHOLD_DAYS)
            active_subq = (
                db.query(SalesSummary.department_id)
                .filter(SalesSummary.date >= threshold_date)
                .distinct()
                .subquery()
            )
            departments_query = departments_query.filter(
                or_(
                    Department.type != "DEPARTMENT",
                    Department.id.in_(active_subq),
                )
            )

        departments = departments_query.all()
        if not departments:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No departments found")

        forecaster = get_forecaster_agent()
        results = []
        current_date = from_date

        while current_date <= to_date:
            for dept in departments:
                try:
                    prediction = forecaster.forecast(str(dept.id), current_date, db)
                except Exception as pred_error:
                    logger.warning(f"Failed to get prediction for {current_date}, {dept.id}: {pred_error}")
                    prediction = None

                results.append({
                    "date": current_date.isoformat(),
                    "department_id": str(dept.id),
                    "department_name": dept.name,
                    "predicted_sales": round(prediction, 2) if prediction else None
                })

            current_date += timedelta(days=1)

        return results

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting batch forecasts: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting batch forecasts: {str(e)}"
        )


@router.get("/export/csv")
async def export_forecasts_csv(
    from_date: date,
    to_date: date,
    department_id: Optional[str] = None,
    include_actual: bool = False,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Export forecasts to CSV format."""
    try:
        if include_actual:
            comparison_data = await get_forecast_comparison(from_date, to_date, department_id, db)
            output = io.StringIO()
            fieldnames = ['date', 'department_name', 'predicted_sales', 'actual_sales', 'error', 'error_percentage']
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            for row in comparison_data:
                writer.writerow({k: row[k] for k in fieldnames})
            filename = f"forecast_comparison_{from_date}_{to_date}.csv"
        else:
            forecast_data = await get_batch_forecasts(from_date, to_date, department_id, db)
            output = io.StringIO()
            fieldnames = ['date', 'department_name', 'predicted_sales']
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            for row in forecast_data:
                writer.writerow({k: row[k] for k in fieldnames})
            filename = f"forecast_{from_date}_{to_date}.csv"

        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting forecasts to CSV: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error exporting forecasts to CSV: {str(e)}"
        )
