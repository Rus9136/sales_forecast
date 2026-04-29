from sqlalchemy import Column, String, ForeignKey, DateTime, Date, CheckConstraint, Boolean
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

    # Segmentation and seasonal fields
    segment_type = Column(
        String(50),
        default='restaurant',
        index=True,
        nullable=True
    )
    season_start_date = Column(Date, nullable=True)
    season_end_date = Column(Date, nullable=True)

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
