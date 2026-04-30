"""SQLAlchemy models for the AI Recommendations subsystem.

Migrated from hr-miniapp. Stores multi-agent analysis runs, per-agent prompt
audit logs, and editable prompt templates.
"""

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from datetime import datetime

from ..db import Base


class AIRecommendation(Base):
    __tablename__ = "ai_recommendations"

    id = Column(Integer, primary_key=True, index=True)
    department_id = Column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    date_start = Column(Date, nullable=False)
    date_end = Column(Date, nullable=False)
    mcp_response = Column(JSONB, nullable=False)
    agent_results = Column(JSONB, nullable=False, default=dict)
    provider = Column(String(50), nullable=False, default="claude")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    department = relationship("Department")
    prompt_logs = relationship(
        "AIPromptLog",
        back_populates="analysis",
        cascade="all, delete-orphan",
    )


class AIPromptLog(Base):
    __tablename__ = "ai_prompt_logs"

    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(
        Integer,
        ForeignKey("ai_recommendations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    agent_name = Column(String(100), nullable=False, index=True)
    provider = Column(String(50), nullable=False)
    full_prompt = Column(Text, nullable=False)
    prompt_length = Column(Integer, nullable=False)
    system_prompt = Column(Text, nullable=True)
    response_text = Column(Text, nullable=True)
    response_length = Column(Integer, nullable=True)
    request_timestamp = Column(
        DateTime, nullable=False, default=datetime.utcnow, index=True
    )
    response_timestamp = Column(DateTime, nullable=True)
    success = Column(Boolean, nullable=False, default=False)
    error_message = Column(Text, nullable=True)
    tokens_used = Column(Integer, nullable=True)

    analysis = relationship("AIRecommendation", back_populates="prompt_logs")


class AIPrompt(Base):
    __tablename__ = "ai_prompts"

    agent_name = Column(String(50), primary_key=True)
    prompt_text = Column(Text, nullable=False)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
