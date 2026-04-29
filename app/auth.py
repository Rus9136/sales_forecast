"""
Authentication and authorization system for API access
"""

from fastapi import HTTPException, Security, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import Column, String, DateTime, Boolean, Integer
from collections import deque
from datetime import datetime, timedelta
from typing import Optional
import threading
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


class InMemoryRateLimiter:
    """
    In-memory sliding window rate limiter.
    Replaces 3 SQL COUNT queries per request with O(1) dict/deque lookups.
    """

    def __init__(self):
        self._lock = threading.Lock()
        # key_id -> deque of timestamps (sorted ascending)
        self._requests: dict[str, deque] = {}

    def _prune(self, key_id: str, now: datetime) -> deque:
        """Remove entries older than 24h (the largest window)."""
        dq = self._requests.get(key_id)
        if dq is None:
            dq = deque()
            self._requests[key_id] = dq
        cutoff = now - timedelta(days=1)
        while dq and dq[0] < cutoff:
            dq.popleft()
        return dq

    def check_and_record(
        self,
        key_id: str,
        limit_minute: int,
        limit_hour: int,
        limit_day: int,
    ) -> bool:
        """
        Check rate limits and record the request if within limits.
        Returns True if allowed, False if rate-limited.
        """
        now = datetime.utcnow()
        with self._lock:
            dq = self._prune(key_id, now)

            minute_ago = now - timedelta(minutes=1)
            hour_ago = now - timedelta(hours=1)

            minute_count = 0
            hour_count = 0
            day_count = len(dq)

            for ts in reversed(dq):
                if ts >= minute_ago:
                    minute_count += 1
                if ts >= hour_ago:
                    hour_count += 1
                else:
                    break  # older entries are only day-level

            if minute_count >= limit_minute:
                return False
            if hour_count >= limit_hour:
                return False
            if day_count >= limit_day:
                return False

            dq.append(now)
            return True


# Module-level singleton
_rate_limiter = InMemoryRateLimiter()


def get_current_api_key_with_rate_limit(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: Session = Depends(get_db)
) -> ApiKey:
    """
    Validate API key and check rate limits (in-memory, zero SQL for rate checks).
    """
    api_key = get_current_api_key(credentials, db)

    # In-memory rate limit check (0 SQL queries)
    allowed = _rate_limiter.check_and_record(
        key_id=api_key.key_id,
        limit_minute=api_key.rate_limit_per_minute,
        limit_hour=api_key.rate_limit_per_hour,
        limit_day=api_key.rate_limit_per_day,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please reduce request frequency."
        )

    return api_key


def log_api_usage(
    api_key: ApiKey,
    endpoint: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    db: Session = None
):
    """Log API usage to DB for analytics (not used for rate limiting)."""
    if db:
        usage_log = ApiKeyUsage(
            key_id=api_key.key_id,
            endpoint=endpoint,
            ip_address=ip_address,
            user_agent=user_agent
        )
        db.add(usage_log)
        db.commit()


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


def get_api_key_or_bypass(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    db: Session = Depends(get_db)
) -> Optional[ApiKey]:
    """
    Validate API key. In DEBUG mode, validate against API_TOKEN from env
    instead of the database (allows dev without DB-stored keys).
    In production mode, use full database-based validation with rate limiting.
    """
    if settings.DEBUG:
        # In debug mode, validate against env token (no DB lookup required)
        if not credentials:
            return None
        if settings.API_TOKEN and credentials.credentials == settings.API_TOKEN:
            return None
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Production: full database-based validation with rate limiting
    return get_current_api_key_with_rate_limit(credentials, db)