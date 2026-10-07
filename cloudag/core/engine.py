import asyncio
from datetime import datetime, timezone
import time
import traceback
from typing import Any, Dict, List, Optional, Set
import uuid
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cloudag.core.graph import WorkflowGraph
from cloudag.core.interpolator import VariableInterpolator
from cloudag.executors.base import BaseExecutor, ExecutionContext
from cloudag.executors.data_transform import DataTransformExecutor
from cloudag.executors.http import HTTPExecutor
from cloudag.executors.llm_agent import LLMAgentExecutor
from cloudag.executors.python_fn import PythonFnExecutor
from cloudag.models.schema import StepDefinition, StepType, WorkflowDefinition
from cloudag.models.state import ExecutionStatus, StepRun, WorkflowRun
from cloudag.storage.repository import WorkflowRepository, compute_input_hash

logger = structlog.get_logger(__name__)


class WorkflowEngine:
    """Async DAG workflow orchestration engine with parallel execution, checkpointing, and caching."""

    def __init__(
        self,
        repository: WorkflowRepository,
        executors: Optional[Dict[StepType, BaseExecutor]] = None,
    ):
        self.repository = repository
        self.executors: Dict[StepType, BaseExecutor] = executors or {
            StepType.HTTP_DISPATCH: HTTPExecutor(),
            StepType.PYTHON_WORKER: PythonFnExecutor(),
            StepType.LLM_AGENT: LLMAgentExecutor(),
            StepType.DATA_TRANSFORM: DataTransformExecutor(),
        }
        # Webhook waiting futures: (run_id, step_id) -> asyncio.Future
        self._webhook_futures: Dict[tuple[str, str], asyncio.Future] = {}

    def deliver_webhook(self, run_id: str, step_id: str, payload: Any) -> bool:
        """Delivers an external webhook payload to an active waiting step."""
        key = (run_id, step_id)
        future = self._webhook_futures.get(key)
        if future and not future.done():
            future.set_result(payload)
            return True
        return False

    async def execute_workflow(
        self,
        workflow: WorkflowDefinition,
        inputs: Dict[str, Any],
        run_id: Optional[str] = None,
    ) -> WorkflowRun:
        """Executes a workflow definition against provided inputs from start to finish."""
        # 1. Validate DAG
        graph = WorkflowGraph(workflow)

        # 2. Persist workflow definition
        await self.repository.save_workflow_definition(workflow)

        # 3. Create initial WorkflowRun
        actual_run_id = run_id or str(uuid.uuid4())
        run = await self.repository.create_workflow_run(
            run_id=actual_run_id,
            workflow_id=workflow.workflow_id,
            inputs=inputs,
            status=ExecutionStatus.RUNNING,
        )

        logger.info(
            "workflow_started",
            run_id=actual_run_id,
            workflow_id=workflow.workflow_id,
            step_count=len(workflow.steps),
        )

        # 4. Execute DAG
        return await self._run_dag(workflow, graph, run, inputs, completed_outputs={})

    async def resume_run(
        self,
        run_id: str,
        workflow: Optional[WorkflowDefinition] = None,
    ) -> WorkflowRun:
        """Resumes a failed or interrupted workflow run, skipping already COMPLETED steps."""
        run = await self.repository.get_workflow_run(run_id)
        if not run:
            raise ValueError(f"WorkflowRun with ID '{run_id}' not found.")

        # Load workflow definition if not provided
        if not workflow:
            workflow = await self.repository.get_workflow_definition(run.workflow_id)
            if not workflow:
                raise ValueError(f"WorkflowDefinition for '{run.workflow_id}' not found.")

        graph = WorkflowGraph(workflow)

        # Collect already completed step outputs
        completed_outputs: Dict[str, Any] = {}
        completed_step_ids: Set[str] = set()

        for step_run in run.step_runs:
            if step_run.status == ExecutionStatus.COMPLETED.value:
                completed_outputs[step_run.step_id] = step_run.outputs
                completed_step_ids.add(step_run.step_id)

        logger.info(
            "workflow_resumed",
            run_id=run_id,
            workflow_id=workflow.workflow_id,
            already_completed=list(completed_step_ids),
        )

        # Mark workflow as RUNNING
        await self.repository.update_workflow_run_status(run_id, ExecutionStatus.RUNNING)

        return await self._run_dag(
            workflow,
            graph,
            run,
            run.inputs,
            completed_outputs=completed_outputs,
        )

    async def _run_dag(
        self,
        workflow: WorkflowDefinition,
        graph: WorkflowGraph,
        run: WorkflowRun,
        workflow_inputs: Dict[str, Any],
        completed_outputs: Dict[str, Any],
    ) -> WorkflowRun:
        run_id = run.id
        steps_map = {step.id: step for step in workflow.steps}
        known_step_ids = set(steps_map.keys())

        # Remaining dependencies tracking for each step
        remaining_deps: Dict[str, Set[str]] = {}
        for step in workflow.steps:
            if step.id in completed_outputs:
                continue
            # Filter dependencies: only keep uncompleted ones
            uncompleted = {dep for dep in step.depends_on if dep not in completed_outputs}
            remaining_deps[step.id] = uncompleted

        active_tasks: Dict[str, asyncio.Task] = {}
        step_run_records: Dict[str, StepRun] = {}
        failed_step_info: Optional[tuple[str, str]] = None
        cancellation_event = asyncio.Event()

        async def execute_single_step(step: StepDefinition) -> Any:
            nonlocal failed_step_info
            step_id = step.id
            t0 = time.perf_counter()

            # 1. Variable interpolation
            interpolator = VariableInterpolator(
                workflow_inputs=workflow_inputs,
                completed_step_outputs=completed_outputs,
                known_step_ids=known_step_ids,
            )

            try:
                resolved_inputs = interpolator.interpolate(step.inputs)
            except Exception as e:
                err_msg = f"Variable interpolation failed for step '{step_id}': {str(e)}"
                logger.error("step_interpolation_failed", run_id=run_id, step_id=step_id, error=err_msg)
                failed_step_info = (step_id, err_msg)
                raise RuntimeError(err_msg) from e

            # Compute input hash
            input_hash = compute_input_hash(step.action, resolved_inputs)

            # Check cache if enabled
            if step.cache_executed_step:
                cached_step = await self.repository.find_cached_step_run(input_hash)
                if cached_step:
                    duration_ms = (time.perf_counter() - t0) * 1000
                    logger.info(
                        "step_cache_hit",
                        run_id=run_id,
                        step_id=step_id,
                        input_hash=input_hash,
                        duration_ms=round(duration_ms, 2),
                    )
                    # Persist cached step run atomically
                    step_run = await self.repository.create_step_run(
                        run_id=run_id,
                        step_id=step_id,
                        input_hash=input_hash,
                        raw_inputs=step.inputs,
                        resolved_inputs=resolved_inputs,
                        status=ExecutionStatus.COMPLETED,
                        outputs=cached_step.outputs,
                        duration_ms=duration_ms,
                        cached=True,
                    )
                    step_run_records[step_id] = step_run
                    return cached_step.outputs

            # Create step run in DB as RUNNING
            step_run = await self.repository.create_step_run(
                run_id=run_id,
                step_id=step_id,
                input_hash=input_hash,
                raw_inputs=step.inputs,
                resolved_inputs=resolved_inputs,
                status=ExecutionStatus.RUNNING,
            )
            step_run_records[step_id] = step_run

            logger.info("step_started", run_id=run_id, step_id=step_id, action=step.action)

            # Check if step is an external webhook receiver
            if resolved_inputs.get("wait_for_webhook") is True:
                webhook_fut: asyncio.Future = asyncio.get_running_loop().create_future()
                self._webhook_futures[(run_id, step_id)] = webhook_fut
                await self.repository.update_step_run(
                    step_run_id=step_run.id,
                    status=ExecutionStatus.WAITING_WEBHOOK,
                )
                try:
                    output = await asyncio.wait_for(webhook_fut, timeout=step.timeout_seconds)
                    duration_ms = (time.perf_counter() - t0) * 1000
                    await self.repository.update_step_run(
                        step_run_id=step_run.id,
                        status=ExecutionStatus.COMPLETED,
                        outputs=output,
                        duration_ms=duration_ms,
                    )
                    logger.info("step_webhook_received", run_id=run_id, step_id=step_id, duration_ms=round(duration_ms, 2))
                    return output
                except Exception as e:
                    duration_ms = (time.perf_counter() - t0) * 1000
                    await self.repository.update_step_run(
                        step_run_id=step_run.id,
                        status=ExecutionStatus.FAILED,
                        error_trace=str(e),
                        duration_ms=duration_ms,
                    )
                    failed_step_info = (step_id, str(e))
                    raise
                finally:
                    self._webhook_futures.pop((run_id, step_id), None)

            # Normal executor dispatch with retry policy
            executor = self.executors.get(step.type)
            if not executor:
                err_msg = f"No executor registered for step type '{step.type}'."
                failed_step_info = (step_id, err_msg)
                await self.repository.update_step_run(
                    step_run_id=step_run.id,
                    status=ExecutionStatus.FAILED,
                    error_trace=err_msg,
                )
                raise ValueError(err_msg)

            context = ExecutionContext(run_id=run_id, workflow_id=workflow.workflow_id, step_id=step_id)

            max_retries = step.retry_policy.max_retries if step.retry_policy else 0
            backoff_factor = step.retry_policy.backoff_factor if step.retry_policy else 1.0

            attempt = 0
            last_err = None

            while attempt <= max_retries:
                if cancellation_event.is_set():
                    raise asyncio.CancelledError()

                try:
                    output = await asyncio.wait_for(
                        executor.execute(step, resolved_inputs, context),
                        timeout=step.timeout_seconds,
                    )
                    duration_ms = (time.perf_counter() - t0) * 1000
                    await self.repository.update_step_run(
                        step_run_id=step_run.id,
                        status=ExecutionStatus.COMPLETED,
                        outputs=output,
                        duration_ms=duration_ms,
                        cached=False,
                    )
                    logger.info(
                        "step_completed",
                        run_id=run_id,
                        step_id=step_id,
                        duration_ms=round(duration_ms, 2),
                        cached=False,
                    )
                    return output
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    last_err = e
                    attempt += 1
                    if attempt <= max_retries:
                        sleep_time = backoff_factor * (2 ** (attempt - 1))
                        logger.warning(
                            "step_retrying",
                            run_id=run_id,
                            step_id=step_id,
                            attempt=attempt,
                            max_retries=max_retries,
                            sleep_seconds=sleep_time,
                            error=str(e),
                        )
                        await asyncio.sleep(sleep_time)

            # Step failed after retries
            duration_ms = (time.perf_counter() - t0) * 1000
            err_trace = f"{str(last_err)}\n{traceback.format_exc()}"
            await self.repository.update_step_run(
                step_run_id=step_run.id,
                status=ExecutionStatus.FAILED,
                error_trace=err_trace,
                duration_ms=duration_ms,
            )
            logger.error(
                "step_failed",
                run_id=run_id,
                step_id=step_id,
                duration_ms=round(duration_ms, 2),
                error=str(last_err),
            )
            failed_step_info = (step_id, str(last_err))
            raise last_err

        # Launch initially ready steps (fan-out)
        for s_id, deps in list(remaining_deps.items()):
            if len(deps) == 0:
                step_def = steps_map[s_id]
                task = asyncio.create_task(execute_single_step(step_def))
                active_tasks[s_id] = task
                del remaining_deps[s_id]

        # Execution loop with fan-in synchronization
        while active_tasks:
            # Wait for at least one active task to complete
            done, _ = await asyncio.wait(
                active_tasks.values(),
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in done:
                # Find corresponding step_id
                finished_step_id = next(s_id for s_id, t in active_tasks.items() if t == task)
                del active_tasks[finished_step_id]

                if task.cancelled():
                    continue

                exc = task.exception()
                if exc is not None:
                    # Failure in a branch: cancel all other active tasks cleanly
                    cancellation_event.set()
                    for other_id, other_task in list(active_tasks.items()):
                        other_task.cancel()

                    # Wait for cancelled tasks to settle
                    if active_tasks:
                        await asyncio.gather(*active_tasks.values(), return_exceptions=True)

                    # Mark any pending/cancelled steps
                    for other_id in active_tasks.keys():
                        if other_id in step_run_records:
                            sr = step_run_records[other_id]
                            try:
                                await self.repository.update_step_run(
                                    step_run_id=sr.id,
                                    status=ExecutionStatus.CANCELLED,
                                    error_trace="Cancelled due to sibling task failure",
                                )
                            except Exception:
                                pass

                    failing_step, failing_err = failed_step_info or (finished_step_id, str(exc))
                    err_msg = f"Workflow failed at step '{failing_step}': {failing_err}"

                    await self.repository.update_workflow_run_status(
                        run_id=run_id,
                        status=ExecutionStatus.FAILED,
                        error_message=err_msg,
                    )
                    logger.error("workflow_failed", run_id=run_id, failing_step=failing_step, error=err_msg)
                    raise RuntimeError(err_msg) from exc

                # Task completed successfully
                output_val = task.result()
                completed_outputs[finished_step_id] = output_val

                # Unlock downstream dependents (fan-in barrier)
                for s_id, deps in list(remaining_deps.items()):
                    if finished_step_id in deps:
                        deps.remove(finished_step_id)
                        if len(deps) == 0:
                            # All upstream dependencies resolved! Schedule step immediately
                            step_def = steps_map[s_id]
                            new_task = asyncio.create_task(execute_single_step(step_def))
                            active_tasks[s_id] = new_task
                            del remaining_deps[s_id]

        # All steps resolved!
        final_run = await self.repository.update_workflow_run_status(
            run_id=run_id,
            status=ExecutionStatus.COMPLETED,
            outputs=completed_outputs,
        )
        logger.info("workflow_completed", run_id=run_id, step_count=len(completed_outputs))
        return final_run or run
