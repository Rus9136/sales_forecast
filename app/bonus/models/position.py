from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from datetime import datetime
from ...db import Base


class BonusPosition(Base):
    __tablename__ = "bonus_position"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    category = Column(String(50), nullable=False)
    iiko_role_code = Column(String(50), nullable=True, index=True)
    iiko_role_name = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
