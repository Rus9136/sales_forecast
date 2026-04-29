"""Forecast post-processing and settings endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
import logging
import traceback

from ...db import get_db
from ...agents.sales_forecaster_agent import get_forecaster_agent
from ...models.branch import SalesSummary, PostprocessingSettings
from ...auth import get_api_key_or_bypass, ApiKey, log_api_usage

logger = logging.getLogger(__name__)

router = APIRouter()


class PostprocessingSettingsRequest(BaseModel):
    enable_smoothing: bool = True
    max_change_percent: float = 50.0
    enable_business_rules: bool = True
    enable_weekend_adjustment: bool = True
    enable_holiday_adjustment: bool = True
    enable_anomaly_detection: bool = True
    anomaly_threshold: float = 3.0
    enable_confidence: bool = True
    confidence_level: float = 0.95


class PostprocessingSettingsResponse(BaseModel):
    id: int
    enable_smoothing: bool
    max_change_percent: float
    enable_business_rules: bool
    enable_weekend_adjustment: bool
    enable_holiday_adjustment: bool
    enable_anomaly_detection: bool
    anomaly_threshold: float
    enable_confidence: bool
    confidence_level: float
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TemporalSmoothingRequest(BaseModel):
    max_change_threshold: float = 0.5
    lookback_weeks: int = 4
    enable_smoothing: bool = True


class PostprocessingOptionsRequest(BaseModel):
    apply_smoothing: Optional[bool] = True
    apply_business_rules: Optional[bool] = True
    apply_anomaly_detection: Optional[bool] = True
    calculate_confidence: Optional[bool] = True
    max_change_percent: Optional[float] = 50.0
    confidence_level: Optional[float] = 0.95


@router.post("/postprocess")
async def postprocess_forecast(
    branch_id: str,
    forecast_date: date,
    raw_prediction: float,
    apply_smoothing: bool = True,
    apply_business_rules: bool = True,
    apply_anomaly_detection: bool = True,
    calculate_confidence: bool = True,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Apply post-processing to a raw forecast prediction."""
    try:
        from ...services.forecast_postprocessing_service import get_forecast_postprocessing_service

        postprocessing_service = get_forecast_postprocessing_service(db)
        result = postprocessing_service.process_forecast(
            branch_id=branch_id,
            forecast_date=forecast_date,
            raw_prediction=raw_prediction,
            apply_smoothing=apply_smoothing,
            apply_business_rules=apply_business_rules,
            apply_anomaly_detection=apply_anomaly_detection,
            calculate_confidence=calculate_confidence
        )

        return {"status": "success", "result": result}

    except Exception as e:
        logger.error(f"Error in forecast post-processing: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error in forecast post-processing: {str(e)}"
        )


@router.post("/postprocess/batch")
async def postprocess_batch_forecasts(
    forecasts: List[Dict[str, Any]],
    apply_smoothing: bool = True,
    apply_business_rules: bool = True,
    apply_anomaly_detection: bool = True,
    calculate_confidence: bool = True,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Apply post-processing to a batch of forecasts."""
    try:
        from ...services.forecast_postprocessing_service import get_forecast_postprocessing_service

        postprocessing_service = get_forecast_postprocessing_service(db)
        processing_options = {
            'apply_smoothing': apply_smoothing,
            'apply_business_rules': apply_business_rules,
            'apply_anomaly_detection': apply_anomaly_detection,
            'calculate_confidence': calculate_confidence
        }

        results = postprocessing_service.batch_process_forecasts(forecasts, **processing_options)

        return {"status": "success", "processed_count": len(results), "results": results}

    except Exception as e:
        logger.error(f"Error in batch forecast post-processing: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error in batch forecast post-processing: {str(e)}"
        )


@router.get("/batch_with_postprocessing")
async def get_batch_forecasts_with_postprocessing(
    from_date: date,
    to_date: date,
    department_id: Optional[str] = None,
    apply_postprocessing: bool = True,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Get batch forecasts with automatic post-processing applied."""
    try:
        if api_key:
            log_api_usage(api_key, "/forecast/batch_with_postprocessing", db=db)

        from .core import get_batch_forecasts
        raw_forecasts = await get_batch_forecasts(from_date, to_date, department_id, db)

        if not apply_postprocessing:
            return raw_forecasts

        from ...services.forecast_postprocessing_service import get_forecast_postprocessing_service
        postprocessing_service = get_forecast_postprocessing_service(db)

        forecast_list = [
            {
                'branch_id': f['department_id'],
                'forecast_date': f['date'],
                'prediction': f['predicted_sales']
            }
            for f in raw_forecasts if f['predicted_sales'] is not None
        ]

        processed_results = postprocessing_service.batch_process_forecasts(forecast_list)

        processed_forecasts = []
        proc_idx = 0
        for original_forecast in raw_forecasts:
            if original_forecast['predicted_sales'] is not None and proc_idx < len(processed_results):
                processed = processed_results[proc_idx]
                enhanced_forecast = original_forecast.copy()
                enhanced_forecast.update({
                    'raw_prediction': processed.get('raw_prediction'),
                    'processed_prediction': processed.get('processed_prediction'),
                    'adjustments_applied': processed.get('adjustments_applied', []),
                    'confidence_interval': processed.get('confidence_interval'),
                    'anomaly_score': processed.get('anomaly_score'),
                    'is_anomaly': processed.get('is_anomaly', False),
                    'business_flags': processed.get('business_flags', [])
                })
                processed_forecasts.append(enhanced_forecast)
                proc_idx += 1
            else:
                processed_forecasts.append(original_forecast)

        return processed_forecasts

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting batch forecasts with post-processing: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting batch forecasts with post-processing: {str(e)}"
        )


@router.get("/postprocessing/settings", response_model=PostprocessingSettingsResponse)
async def get_postprocessing_settings(
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Get current active postprocessing settings."""
    try:
        pp_settings = db.query(PostprocessingSettings).filter(
            PostprocessingSettings.is_active == True
        ).first()

        if not pp_settings:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active postprocessing settings found")

        return pp_settings

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting postprocessing settings: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting postprocessing settings: {str(e)}"
        )


@router.post("/postprocessing/settings", response_model=PostprocessingSettingsResponse)
async def save_postprocessing_settings(
    settings_request: PostprocessingSettingsRequest,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Save new postprocessing settings."""
    try:
        db.query(PostprocessingSettings).update({"is_active": False})

        new_settings = PostprocessingSettings(
            enable_smoothing=settings_request.enable_smoothing,
            max_change_percent=settings_request.max_change_percent,
            enable_business_rules=settings_request.enable_business_rules,
            enable_weekend_adjustment=settings_request.enable_weekend_adjustment,
            enable_holiday_adjustment=settings_request.enable_holiday_adjustment,
            enable_anomaly_detection=settings_request.enable_anomaly_detection,
            anomaly_threshold=settings_request.anomaly_threshold,
            enable_confidence=settings_request.enable_confidence,
            confidence_level=settings_request.confidence_level,
            is_active=True
        )

        db.add(new_settings)
        db.commit()
        db.refresh(new_settings)

        logger.info(f"Saved new postprocessing settings: ID {new_settings.id}")
        return new_settings

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving postprocessing settings: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error saving postprocessing settings: {str(e)}"
        )


@router.post("/test_smoothing")
async def test_temporal_smoothing(
    branch_id: str,
    forecast_date: date,
    smoothing_params: Optional[TemporalSmoothingRequest] = None,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Test temporal smoothing with various parameters."""
    try:
        forecaster = get_forecaster_agent()
        raw_prediction = forecaster.forecast(branch_id, forecast_date, db)

        if raw_prediction is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not generate forecast")

        threshold = smoothing_params.max_change_threshold if smoothing_params else 0.5
        smoothed_prediction = forecaster._apply_temporal_smoothing(
            branch_id, forecast_date, raw_prediction, db, threshold
        )

        recent_sales = db.query(SalesSummary.total_sales, SalesSummary.date).filter(
            and_(
                SalesSummary.department_id == branch_id,
                SalesSummary.date >= forecast_date - timedelta(days=28),
                SalesSummary.date < forecast_date
            )
        ).order_by(SalesSummary.date.desc()).limit(10).all()

        historical_context = [
            {"date": row.date.isoformat(), "sales": float(row.total_sales)}
            for row in recent_sales
        ]

        return {
            "status": "success",
            "branch_id": branch_id,
            "forecast_date": forecast_date.isoformat(),
            "raw_prediction": round(raw_prediction, 2),
            "smoothed_prediction": round(smoothed_prediction, 2),
            "smoothing_applied": bool(raw_prediction != smoothed_prediction),
            "change_percent": round(((smoothed_prediction - raw_prediction) / raw_prediction) * 100, 2) if raw_prediction != 0 else 0,
            "parameters": {
                "max_change_threshold": threshold,
                "threshold_percent": f"{threshold * 100}%"
            },
            "historical_context": historical_context
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing temporal smoothing: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error testing temporal smoothing: {str(e)}"
        )
