import asyncio
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from cloudag.models.schema import WorkflowDefinition
from cloudag.models.state import (
    ExecutionStatus,
    StepRun,
    WorkflowDefinitionRecord,
    WorkflowRun,
    utc_now,
)


def compute_input_hash(action: str, resolved_inputs: Dict[str, Any]) -> str:
    """Calculates deterministic SHA-256 hash of (action, resolved_inputs)."""
    canonical_dict = {
        "action": action,
        "inputs": resolved_inputs,
    }
    canonical_json = json.dumps(
        canonical_dict,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class WorkflowRepository:
    """Repository handling persistence of workflows, runs, steps, and cache lookups."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory
        self._lock = asyncio.Lock()
        self._cache_index: Dict[str, StepRun] = {}

    async def save_workflow_definition(self, workflow: WorkflowDefinition) -> WorkflowDefinitionRecord:
        async with self._lock:
            async with self.session_factory() as session:
                async with session.begin():
                    record = await session.get(WorkflowDefinitionRecord, workflow.workflow_id)
                    definition_dict = workflow.model_dump(mode="json")
                    if record:
                        record.version = workflow.version
                        record.definition_json = definition_dict
                        record.updated_at = utc_now()
                    else:
                        record = WorkflowDefinitionRecord(
                            workflow_id=workflow.workflow_id,
                            version=workflow.version,
                            definition_json=definition_dict,
                            created_at=utc_now(),
                            updated_at=utc_now(),
                        )
                        session.add(record)
                    await session.flush()
                    return record

    async def get_workflow_definition(self, workflow_id: str) -> Optional[WorkflowDefinition]:
        async with self._lock:
            async with self.session_factory() as session:
                record = await session.get(WorkflowDefinitionRecord, workflow_id)
                if not record:
                    return None
                return WorkflowDefinition.model_validate(record.definition_json)

    async def create_workflow_run(
        self,
        run_id: str,
        workflow_id: str,
        inputs: Dict[str, Any],
        status: ExecutionStatus = ExecutionStatus.PENDING,
    ) -> WorkflowRun:
        async with self._lock:
            async with self.session_factory() as session:
                async with session.begin():
                    run = WorkflowRun(
                        id=run_id,
                        workflow_id=workflow_id,
                        status=status.value,
                        inputs=inputs,
                        outputs=None,
                        created_at=utc_now(),
                        started_at=utc_now() if status == ExecutionStatus.RUNNING else None,
                    )
                    session.add(run)
                    await session.flush()
                    return run

    async def get_workflow_run(self, run_id: str) -> Optional[WorkflowRun]:
        async with self._lock:
            async with self.session_factory() as session:
                query = (
                    select(WorkflowRun)
                    .where(WorkflowRun.id == run_id)
                    .options(selectinload(WorkflowRun.step_runs))
                )
                result = await session.execute(query)
                return result.scalar_one_or_none()

    async def update_workflow_run_status(
        self,
        run_id: str,
        status: ExecutionStatus,
        outputs: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> Optional[WorkflowRun]:
        async with self._lock:
            async with self.session_factory() as session:
                async with session.begin():
                    run = await session.get(WorkflowRun, run_id)
                    if not run:
                        return None
                    run.status = status.value
                    if status == ExecutionStatus.RUNNING and not run.started_at:
                        run.started_at = utc_now()
                    elif status in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED):
                        run.completed_at = utc_now()
                    if outputs is not None:
                        run.outputs = outputs
                    if error_message is not None:
                        run.error_message = error_message
                    await session.flush()
                    return run

    async def create_step_run(
        self,
        run_id: str,
        step_id: str,
        input_hash: str,
        raw_inputs: Dict[str, Any],
        resolved_inputs: Dict[str, Any],
        status: ExecutionStatus = ExecutionStatus.PENDING,
        outputs: Optional[Any] = None,
        duration_ms: Optional[float] = None,
        cached: bool = False,
    ) -> StepRun:
        async with self._lock:
            async with self.session_factory() as session:
                async with session.begin():
                    step_run = StepRun(
                        run_id=run_id,
                        step_id=step_id,
                        input_hash=input_hash,
                        raw_inputs=raw_inputs,
                        resolved_inputs=resolved_inputs,
                        status=status.value,
                        outputs=outputs,
                        duration_ms=duration_ms,
                        cached=cached,
                        created_at=utc_now(),
                        started_at=utc_now() if status in (ExecutionStatus.RUNNING, ExecutionStatus.COMPLETED) else None,
                        completed_at=utc_now() if status == ExecutionStatus.COMPLETED else None,
                    )
                    session.add(step_run)
                    await session.flush()
                    return step_run

    async def get_step_run(self, run_id: str, step_id: str) -> Optional[StepRun]:
        async with self._lock:
            async with self.session_factory() as session:
                query = select(StepRun).where(
                    StepRun.run_id == run_id,
                    StepRun.step_id == step_id,
                )
                result = await session.execute(query)
                return result.scalar_one_or_none()

    async def update_step_run(
        self,
        step_run_id: str,
        status: ExecutionStatus,
        outputs: Optional[Any] = None,
        error_trace: Optional[str] = None,
        duration_ms: Optional[float] = None,
        cached: bool = False,
    ) -> Optional[StepRun]:
        async with self._lock:
            async with self.session_factory() as session:
                async with session.begin():
                    step_run = await session.get(StepRun, step_run_id)
                    if not step_run:
                        return None
                    step_run.status = status.value
                    if status == ExecutionStatus.RUNNING and not step_run.started_at:
                        step_run.started_at = utc_now()
                    elif status in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED):
                        step_run.completed_at = utc_now()
                    if outputs is not None:
                        step_run.outputs = outputs
                    if error_trace is not None:
                        step_run.error_trace = error_trace
                    if duration_ms is not None:
                        step_run.duration_ms = duration_ms
                    if status == ExecutionStatus.COMPLETED:
                        self._cache_index[step_run.input_hash] = step_run
                    return step_run

    async def find_cached_step_run(self, input_hash: str) -> Optional[StepRun]:
        """Looks up a previously completed StepRun with the matching input_hash."""
        if input_hash in self._cache_index:
            return self._cache_index[input_hash]

        async with self._lock:
            if input_hash in self._cache_index:
                return self._cache_index[input_hash]
            async with self.session_factory() as session:
                query = (
                    select(StepRun)
                    .where(
                        StepRun.input_hash == input_hash,
                        StepRun.status == ExecutionStatus.COMPLETED.value,
                    )
                    .order_by(StepRun.completed_at.desc())
                    .limit(1)
                )
                result = await session.execute(query)
                found = result.scalar_one_or_none()
                if found:
                    self._cache_index[input_hash] = found
                return found
