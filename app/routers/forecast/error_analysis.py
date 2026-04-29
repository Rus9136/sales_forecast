"""Error analysis endpoints for forecast quality investigation."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import date
from typing import Optional
import logging

from ...db import get_db
from ...auth import get_api_key_or_bypass, ApiKey

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/error-analysis")


@router.get("/errors_by_segment")
async def analyze_errors_by_segment(
    from_date: date,
    to_date: date,
    segment_type: str = "department",
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Analyze prediction errors by different segments."""
    try:
        from ...services.error_analysis_service import get_error_analysis_service

        analysis_service = get_error_analysis_service(db)
        results = analysis_service.analyze_errors_by_segment(from_date, to_date, segment_type)

        return {
            "status": "success",
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "segment_type": segment_type,
            "analysis": results
        }

    except Exception as e:
        logger.error(f"Error analyzing errors by segment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error analyzing errors by segment: {str(e)}"
        )


@router.get("/problematic_branches")
async def identify_problematic_branches(
    from_date: date,
    to_date: date,
    min_samples: int = 5,
    mape_threshold: float = 15.0,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Identify branches with consistently high prediction errors."""
    try:
        from ...services.error_analysis_service import get_error_analysis_service

        analysis_service = get_error_analysis_service(db)
        problematic_branches = analysis_service.identify_problematic_branches(
            from_date, to_date, min_samples, mape_threshold
        )

        return {
            "status": "success",
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "criteria": {"min_samples": min_samples, "mape_threshold": mape_threshold},
            "problematic_branches_count": len(problematic_branches),
            "problematic_branches": problematic_branches
        }

    except Exception as e:
        logger.error(f"Error identifying problematic branches: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error identifying problematic branches: {str(e)}"
        )


@router.get("/temporal_errors")
async def analyze_temporal_errors(
    from_date: date,
    to_date: date,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Analyze how prediction errors vary over time."""
    try:
        from ...services.error_analysis_service import get_error_analysis_service

        analysis_service = get_error_analysis_service(db)
        temporal_analysis = analysis_service.analyze_temporal_errors(from_date, to_date)

        return {
            "status": "success",
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "temporal_analysis": temporal_analysis
        }

    except Exception as e:
        logger.error(f"Error analyzing temporal errors: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error analyzing temporal errors: {str(e)}"
        )


@router.get("/error_distribution")
async def get_error_distribution(
    from_date: date,
    to_date: date,
    department_id: Optional[str] = None,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Get distribution of prediction errors for statistical analysis."""
    try:
        from ...services.error_analysis_service import get_error_analysis_service

        analysis_service = get_error_analysis_service(db)
        distribution = analysis_service.get_error_distribution(from_date, to_date, department_id)

        return {
            "status": "success",
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "department_id": department_id,
            "error_distribution": distribution
        }

    except Exception as e:
        logger.error(f"Error getting error distribution: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting error distribution: {str(e)}"
        )
