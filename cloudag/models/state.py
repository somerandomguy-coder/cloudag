from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class ExecutionStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    WAITING_WEBHOOK = "WAITING_WEBHOOK"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class WorkflowDefinitionRecord(Base):
    __tablename__ = "workflow_definitions"

    workflow_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False, default="1.0.0")
    definition_json: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default=ExecutionStatus.PENDING.value, index=True, nullable=False)
    inputs: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    outputs: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    step_runs: Mapped[List["StepRun"]] = relationship(
        "StepRun",
        back_populates="workflow_run",
        cascade="all, delete-orphan",
        order_by="StepRun.created_at",
    )

    def __init__(self, **kwargs: Any):
        if "id" not in kwargs or kwargs["id"] is None:
            kwargs["id"] = str(uuid.uuid4())
        super().__init__(**kwargs)


class StepRun(Base):
    __tablename__ = "step_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    step_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default=ExecutionStatus.PENDING.value, index=True, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    
    raw_inputs: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    resolved_inputs: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    outputs: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    error_trace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    duration_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cached: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    workflow_run: Mapped["WorkflowRun"] = relationship("WorkflowRun", back_populates="step_runs")

    __table_args__ = (
        Index("ix_step_runs_input_hash_status", "input_hash", "status"),
        Index("ix_step_runs_run_step", "run_id", "step_id"),
    )

    def __init__(self, **kwargs: Any):
        if "id" not in kwargs or kwargs["id"] is None:
            kwargs["id"] = str(uuid.uuid4())
        super().__init__(**kwargs)
