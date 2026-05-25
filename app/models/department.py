from sqlalchemy import Column, String, ForeignKey, DateTime, Date, CheckConstraint, Boolean, SmallInteger
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid
from ..db import Base


class Department(Base):
    __tablename__ = "departments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True, index=True)
    code = Column(String(50), nullable=True, index=True)
    code_tco = Column(String(50), nullable=True)
    name = Column(String(255), nullable=False)
    type = Column(String(50), default='DEPARTMENT', index=True)
    taxpayer_id_number = Column(String(50), nullable=True)

    # Which iiko server this department was synced from (e.g. "sandy-co-co.iiko.it",
    # "madlen-group-so.iiko.it"). This is the only reliable source-of-truth for
    # separating Сандык vs Мадлен catalogs — `taxpayer_id_number` is empty for 47/91
    # departments. Populated by `iiko_department_loader` on every sync.
    iiko_source_domain = Column(String, nullable=False, index=True)

    # Segmentation and seasonal fields
    segment_type = Column(
        String(50),
        default='restaurant',
        index=True,
        nullable=True
    )
    season_start_date = Column(Date, nullable=True)
    season_end_date = Column(Date, nullable=True)

    # Operational characteristics (manual-only, used as ML features).
    # iiko sync MUST NOT overwrite these — see iiko_department_loader.py.
    brand = Column(String(50), nullable=True, index=True)
    location_type = Column(String(30), nullable=True, index=True)
    tourist_traffic_dependent = Column(Boolean, nullable=False, default=False)
    is_24_7 = Column(Boolean, nullable=False, default=False)
    opening_hour = Column(SmallInteger, nullable=True)
    closing_hour = Column(SmallInteger, nullable=True)
    seasonality_intensity = Column(String(10), nullable=False, default='none')
    city = Column(String(100), nullable=True)
    opened_date = Column(Date, nullable=True)
    season_start_month = Column(SmallInteger, nullable=True)
    season_end_month = Column(SmallInteger, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    synced_at = Column(DateTime, default=datetime.utcnow)

    # Self-referential relationship for hierarchy
    children = relationship("Department", back_populates="parent")
    parent = relationship("Department", back_populates="children", remote_side=[id])

    __table_args__ = (
        CheckConstraint(
            segment_type.in_([
                'coffeehouse',
                'restaurant',
                'confectionery',
                'food_court',
                'store',
                'fast_food',
                'bakery',
                'cafe',
                'bar'
            ]),
            name='valid_segment_type'
        ),
    )
