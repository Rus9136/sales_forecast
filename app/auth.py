"""
Authentication and authorization system for API access
"""

from fastapi import HTTPException, Security, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import Column, String, DateTime, Boolean, Integer
from datetime import datetime, timedelta
from typing import Optional
import secrets
import hashlib
from .db import Base, get_db
from .config import settings


# Security scheme
security = HTTPBearer()


class ApiKey(Base):
    """API Key model for external access"""
    __tablename__ = "api_keys"
    
    id = Column(Integer, primary_key=True, index=True)
    key_id = Column(String(32), unique=True, index=True, nullable=False)
    key_hash = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    rate_limit_per_minute = Column(Integer, default=100, nullable=False)
    rate_limit_per_hour = Column(Integer, default=1000, nullable=False)
    rate_limit_per_day = Column(Integer, default=10000, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    created_by = Column(String(100), nullable=True)


class ApiKeyUsage(Base):
    """Track API key usage for rate limiting"""
    __tablename__ = "api_key_usage"
    
    id = Column(Integer, primary_key=True, index=True)
    key_id = Column(String(32), index=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    endpoint = Column(String(200), nullable=False)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)


def generate_api_key() -> tuple[str, str]:
    """
    Generate a new API key pair
    
    Returns:
        tuple: (key_id, secret_key) - key_id is stored, secret_key is returned once
    """
    key_id = secrets.token_urlsafe(24)  # 32 chars
    secret_key = secrets.token_urlsafe(32)  # 43 chars
    
    # Create full API key in format: sf_keyid_secret
    full_key = f"sf_{key_id}_{secret_key}"
    
    return key_id, full_key


def hash_api_key(api_key: str) -> str:
    """Hash an API key for secure storage"""
    return hashlib.sha256(api_key.encode()).hexdigest()


def verify_api_key(provided_key: str, stored_hash: str) -> bool:
    """Verify a provided API key against stored hash"""
    return hashlib.sha256(provided_key.encode()).hexdigest() == stored_hash


def extract_key_id_from_api_key(api_key: str) -> Optional[str]:
    """Extract key_id from full API key"""
    if not api_key.startswith("sf_"):
        return None
    
    # Remove 'sf_' prefix
    remaining = api_key[3:]
    
    # Split by underscore and take first 3 parts for key_id
    # Format: key_id (3 parts) + secret (3 parts)
    parts = remaining.split("_")
    if len(parts) < 6:  # Need at least 6 parts total
        return None
    
    # key_id is first 3 parts joined
    key_id = "_".join(parts[:3])
    return key_id if key_id else None


def get_current_api_key(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: Session = Depends(get_db)
) -> ApiKey:
    """
    Validate API key and return the associated ApiKey object
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    api_key = credentials.credentials
    
    # Extract key_id from the full API key
    key_id = extract_key_id_from_api_key(api_key)
    if not key_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key format",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Find the API key in database
    db_api_key = db.query(ApiKey).filter(
        ApiKey.key_id == key_id,
        ApiKey.is_active == True
    ).first()
    
    if not db_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if key is expired
    if db_api_key.expires_at and db_api_key.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verify the full API key hash
    if not verify_api_key(api_key, db_api_key.key_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Update last used timestamp
    db_api_key.last_used_at = datetime.utcnow()
    db.commit()
    
    return db_api_key


def check_rate_limit(
    api_key: ApiKey,
    endpoint: str,
    db: Session
) -> bool:
    """
    Check if API key has exceeded rate limits
    
    Returns:
        bool: True if within limits, False if exceeded
    """
    now = datetime.utcnow()
    
    # Check minute limit
    minute_ago = now - timedelta(minutes=1)
    minute_usage = db.query(ApiKeyUsage).filter(
        ApiKeyUsage.key_id == api_key.key_id,
        ApiKeyUsage.timestamp >= minute_ago
    ).count()
    
    if minute_usage >= api_key.rate_limit_per_minute:
        return False
    
    # Check hour limit
    hour_ago = now - timedelta(hours=1)
    hour_usage = db.query(ApiKeyUsage).filter(
        ApiKeyUsage.key_id == api_key.key_id,
        ApiKeyUsage.timestamp >= hour_ago
    ).count()
    
    if hour_usage >= api_key.rate_limit_per_hour:
        return False
    
    # Check day limit
    day_ago = now - timedelta(days=1)
    day_usage = db.query(ApiKeyUsage).filter(
        ApiKeyUsage.key_id == api_key.key_id,
        ApiKeyUsage.timestamp >= day_ago
    ).count()
    
    if day_usage >= api_key.rate_limit_per_day:
        return False
    
    return True


def log_api_usage(
    api_key: ApiKey,
    endpoint: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    db: Session = None
):
    """Log API usage for rate limiting and analytics"""
    if db:
        usage_log = ApiKeyUsage(
            key_id=api_key.key_id,
            endpoint=endpoint,
            ip_address=ip_address,
            user_agent=user_agent
        )
        db.add(usage_log)
        db.commit()


def get_current_api_key_with_rate_limit(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: Session = Depends(get_db)
) -> ApiKey:
    """
    Validate API key and check rate limits
    """
    api_key = get_current_api_key(credentials, db)
    
    # Check rate limits
    if not check_rate_limit(api_key, "forecast", db):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please reduce request frequency."
        )
    
    # Log usage
    log_api_usage(api_key, "forecast", db=db)
    
    return api_key


# Optional dependency for endpoints that can work with or without auth
def get_optional_api_key(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    db: Session = Depends(get_db)
) -> Optional[ApiKey]:
    """
    Optional API key validation - allows access without key but tracks usage if provided
    """
    if not credentials:
        return None
    
    try:
        return get_current_api_key(credentials, db)
    except HTTPException:
        return None


# Environment-based auth bypass for development
def get_api_key_or_bypass(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    db: Session = Depends(get_db)
) -> Optional[ApiKey]:
    """
    Get API key or bypass in development mode
    """
    # Bypass authentication in development mode
    if settings.DEBUG:
        return None
    
    # Require authentication in production
    return get_current_api_key_with_rate_limit(credentials, db)