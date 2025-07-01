"""
Authentication and API key management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel

from ..db import get_db
from ..auth import ApiKey, ApiKeyUsage, generate_api_key, hash_api_key, get_api_key_or_bypass


router = APIRouter(prefix="/auth", tags=["authentication"])


class ApiKeyCreate(BaseModel):
    name: str
    description: Optional[str] = None
    expires_in_days: Optional[int] = None  # None means no expiration
    rate_limit_per_minute: Optional[int] = 100
    rate_limit_per_hour: Optional[int] = 1000
    rate_limit_per_day: Optional[int] = 10000
    created_by: Optional[str] = None


class ApiKeyResponse(BaseModel):
    id: int
    key_id: str
    name: str
    description: Optional[str]
    is_active: bool
    rate_limit_per_minute: int
    rate_limit_per_hour: int
    rate_limit_per_day: int
    last_used_at: Optional[datetime]
    created_at: datetime
    expires_at: Optional[datetime]
    created_by: Optional[str]


class ApiKeyCreateResponse(BaseModel):
    key_id: str
    api_key: str  # Full API key - shown only once!
    name: str
    expires_at: Optional[datetime]
    rate_limits: dict


class ApiKeyUsageStats(BaseModel):
    key_id: str
    name: str
    total_requests: int
    requests_last_hour: int
    requests_last_day: int
    last_used_at: Optional[datetime]
    rate_limit_status: dict


@router.post("/keys", response_model=ApiKeyCreateResponse)
async def create_api_key(
    key_data: ApiKeyCreate,
    db: Session = Depends(get_db),
    current_api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """
    Create a new API key
    
    WARNING: The full API key is returned only once and cannot be retrieved again!
    """
    try:
        # Generate new API key
        key_id, full_api_key = generate_api_key()
        key_hash = hash_api_key(full_api_key)
        
        # Calculate expiration date
        expires_at = None
        if key_data.expires_in_days:
            expires_at = datetime.utcnow() + timedelta(days=key_data.expires_in_days)
        
        # Create API key record
        api_key = ApiKey(
            key_id=key_id,
            key_hash=key_hash,
            name=key_data.name,
            description=key_data.description,
            rate_limit_per_minute=key_data.rate_limit_per_minute,
            rate_limit_per_hour=key_data.rate_limit_per_hour,
            rate_limit_per_day=key_data.rate_limit_per_day,
            expires_at=expires_at,
            created_by=key_data.created_by
        )
        
        db.add(api_key)
        db.commit()
        db.refresh(api_key)
        
        return ApiKeyCreateResponse(
            key_id=key_id,
            api_key=full_api_key,  # Full key returned only once!
            name=api_key.name,
            expires_at=api_key.expires_at,
            rate_limits={
                "per_minute": api_key.rate_limit_per_minute,
                "per_hour": api_key.rate_limit_per_hour,
                "per_day": api_key.rate_limit_per_day
            }
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create API key: {str(e)}"
        )


@router.get("/keys", response_model=List[ApiKeyResponse])
async def list_api_keys(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """
    List all API keys (without the actual key values)
    """
    query = db.query(ApiKey)
    
    if not include_inactive:
        query = query.filter(ApiKey.is_active == True)
    
    keys = query.order_by(ApiKey.created_at.desc()).all()
    
    return [
        ApiKeyResponse(
            id=key.id,
            key_id=key.key_id,
            name=key.name,
            description=key.description,
            is_active=key.is_active,
            rate_limit_per_minute=key.rate_limit_per_minute,
            rate_limit_per_hour=key.rate_limit_per_hour,
            rate_limit_per_day=key.rate_limit_per_day,
            last_used_at=key.last_used_at,
            created_at=key.created_at,
            expires_at=key.expires_at,
            created_by=key.created_by
        )
        for key in keys
    ]


@router.get("/keys/{key_id}", response_model=ApiKeyResponse)
async def get_api_key(
    key_id: str,
    db: Session = Depends(get_db)
):
    """
    Get details of a specific API key
    """
    api_key = db.query(ApiKey).filter(ApiKey.key_id == key_id).first()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    return ApiKeyResponse(
        id=api_key.id,
        key_id=api_key.key_id,
        name=api_key.name,
        description=api_key.description,
        is_active=api_key.is_active,
        rate_limit_per_minute=api_key.rate_limit_per_minute,
        rate_limit_per_hour=api_key.rate_limit_per_hour,
        rate_limit_per_day=api_key.rate_limit_per_day,
        last_used_at=api_key.last_used_at,
        created_at=api_key.created_at,
        expires_at=api_key.expires_at,
        created_by=api_key.created_by
    )


@router.delete("/keys/{key_id}")
async def deactivate_api_key(
    key_id: str,
    db: Session = Depends(get_db),
    current_api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """
    Deactivate an API key (soft delete)
    """
    api_key = db.query(ApiKey).filter(ApiKey.key_id == key_id).first()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    api_key.is_active = False
    db.commit()
    
    return {"message": f"API key '{api_key.name}' deactivated successfully"}


@router.post("/keys/{key_id}/activate")
async def activate_api_key(
    key_id: str,
    db: Session = Depends(get_db),
    current_api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """
    Reactivate a deactivated API key
    """
    api_key = db.query(ApiKey).filter(ApiKey.key_id == key_id).first()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    # Check if key is expired
    if api_key.expires_at and api_key.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot activate expired API key"
        )
    
    api_key.is_active = True
    db.commit()
    
    return {"message": f"API key '{api_key.name}' activated successfully"}


@router.get("/keys/{key_id}/usage", response_model=ApiKeyUsageStats)
async def get_api_key_usage(
    key_id: str,
    db: Session = Depends(get_db)
):
    """
    Get usage statistics for an API key
    """
    api_key = db.query(ApiKey).filter(ApiKey.key_id == key_id).first()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    now = datetime.utcnow()
    
    # Total requests
    total_requests = db.query(ApiKeyUsage).filter(
        ApiKeyUsage.key_id == key_id
    ).count()
    
    # Requests in last hour
    hour_ago = now - timedelta(hours=1)
    requests_last_hour = db.query(ApiKeyUsage).filter(
        ApiKeyUsage.key_id == key_id,
        ApiKeyUsage.timestamp >= hour_ago
    ).count()
    
    # Requests in last day
    day_ago = now - timedelta(days=1)
    requests_last_day = db.query(ApiKeyUsage).filter(
        ApiKeyUsage.key_id == key_id,
        ApiKeyUsage.timestamp >= day_ago
    ).count()
    
    # Rate limit status
    minute_ago = now - timedelta(minutes=1)
    requests_last_minute = db.query(ApiKeyUsage).filter(
        ApiKeyUsage.key_id == key_id,
        ApiKeyUsage.timestamp >= minute_ago
    ).count()
    
    return ApiKeyUsageStats(
        key_id=key_id,
        name=api_key.name,
        total_requests=total_requests,
        requests_last_hour=requests_last_hour,
        requests_last_day=requests_last_day,
        last_used_at=api_key.last_used_at,
        rate_limit_status={
            "requests_last_minute": requests_last_minute,
            "minute_limit": api_key.rate_limit_per_minute,
            "minute_remaining": max(0, api_key.rate_limit_per_minute - requests_last_minute),
            "requests_last_hour": requests_last_hour,
            "hour_limit": api_key.rate_limit_per_hour,
            "hour_remaining": max(0, api_key.rate_limit_per_hour - requests_last_hour),
            "requests_last_day": requests_last_day,
            "day_limit": api_key.rate_limit_per_day,
            "day_remaining": max(0, api_key.rate_limit_per_day - requests_last_day)
        }
    )


@router.post("/test")
async def test_api_key(
    api_key: ApiKey = Depends(lambda: None)  # This will be replaced with auth dependency
):
    """
    Test endpoint to verify API key authentication
    """
    if api_key:
        return {
            "message": "API key authentication successful",
            "key_name": api_key.name,
            "key_id": api_key.key_id
        }
    else:
        return {
            "message": "No authentication required (development mode)"
        }