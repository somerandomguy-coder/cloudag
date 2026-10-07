import asyncio
import time
from typing import Any, Dict
import pytest

from cloudag.core.engine import WorkflowEngine
from cloudag.executors.python_fn import PythonFnExecutor
from cloudag.models.schema import StepDefinition, StepType, WorkflowDefinition
from cloudag.models.state import ExecutionStatus
from cloudag.storage.database import create_engine_and_sessionmaker, init_db
from cloudag.storage.repository import WorkflowRepository, compute_input_hash


@pytest.fixture
async def setup_cache_env():
    db_url = "sqlite+aiosqlite:///:memory:"
    engine_obj, session_factory = create_engine_and_sessionmaker(db_url)
    await init_db(engine_obj)
    repo = WorkflowRepository(session_factory)

    py_executor = PythonFnExecutor()
    engine = WorkflowEngine(
        repository=repo,
        executors={StepType.PYTHON_WORKER: py_executor},
    )

    yield engine, repo

    await engine_obj.dispose()


@pytest.mark.asyncio
async def test_step_caching_across_different_runs(setup_cache_env):
    engine, repo = setup_cache_env

    call_count = 0

    def costly_computation(inputs: Dict[str, Any]) -> Dict[str, Any]:
        nonlocal call_count
        call_count += 1
        return {"result": inputs.get("n", 0) ** 2, "calls": call_count}

    PythonFnExecutor.register("costly_computation", costly_computation)

    workflow = WorkflowDefinition(
        workflow_id="caching_test_wf",
        steps=[
            StepDefinition(
                id="calc_step",
                type=StepType.PYTHON_WORKER,
                action="costly_computation",
                inputs={"n": "${workflow.input.n}"},
                cache_executed_step=True,
            )
        ],
    )

    # First run
    run1 = await engine.execute_workflow(workflow, {"n": 5})
    assert run1.status == ExecutionStatus.COMPLETED.value
    assert call_count == 1

    # Second run with identical input
    run2 = await engine.execute_workflow(workflow, {"n": 5})
    assert run2.status == ExecutionStatus.COMPLETED.value
    # Computation must NOT be called again
    assert call_count == 1

    persisted_run2 = await repo.get_workflow_run(run2.id)
    assert persisted_run2.step_runs[0].cached is True
    assert persisted_run2.step_runs[0].outputs["result"] == 25

    # Third run with different input
    run3 = await engine.execute_workflow(workflow, {"n": 6})
    assert run3.status == ExecutionStatus.COMPLETED.value
    assert call_count == 2
    persisted_run3 = await repo.get_workflow_run(run3.id)
    assert persisted_run3.step_runs[0].cached is False
    assert persisted_run3.step_runs[0].outputs["result"] == 36


@pytest.mark.asyncio
async def test_run_resumption_skips_completed_steps(setup_cache_env):
    engine, repo = setup_cache_env

    step1_runs = 0
    step2_runs = 0
    step2_should_fail = True

    def worker_1(inputs: Dict[str, Any]) -> str:
        nonlocal step1_runs
        step1_runs += 1
        return "step1_output"

    def worker_2(inputs: Dict[str, Any]) -> str:
        nonlocal step2_runs, step2_should_fail
        step2_runs += 1
        if step2_should_fail:
            raise RuntimeError("Step 2 transient failure!")
        return "step2_fixed_output"

    PythonFnExecutor.register("worker_1", worker_1)
    PythonFnExecutor.register("worker_2", worker_2)

    workflow = WorkflowDefinition(
        workflow_id="resumption_test_wf",
        steps=[
            StepDefinition(
                id="step_first",
                type=StepType.PYTHON_WORKER,
                action="worker_1",
            ),
            StepDefinition(
                id="step_second",
                type=StepType.PYTHON_WORKER,
                action="worker_2",
                depends_on=["step_first"],
            ),
        ],
    )

    # Execute and expect step 2 to fail
    with pytest.raises(RuntimeError, match="Step 2 transient failure"):
        await engine.execute_workflow(workflow, {}, run_id="test_resume_run_1")

    # Verify state after failure
    run_failed = await repo.get_workflow_run("test_resume_run_1")
    assert run_failed.status == ExecutionStatus.FAILED.value
    assert step1_runs == 1
    assert step2_runs == 1

    # Fix the condition
    step2_should_fail = False

    # Resume the run
    resumed = await engine.resume_run("test_resume_run_1", workflow=workflow)
    assert resumed.status == ExecutionStatus.COMPLETED.value

    # Verify Step 1 was SKIPPED on resumption (run count remains 1)
    assert step1_runs == 1
    # Step 2 was executed again and succeeded
    assert step2_runs == 2

    # Check outputs
    assert resumed.outputs["step_first"] == "step1_output"
    assert resumed.outputs["step_second"] == "step2_fixed_output"


@pytest.mark.asyncio
async def test_webhook_step_delivery(setup_cache_env):
    engine, repo = setup_cache_env

    workflow = WorkflowDefinition(
        workflow_id="webhook_test_wf",
        steps=[
            StepDefinition(
                id="webhook_step",
                type=StepType.PYTHON_WORKER,
                action="none",
                inputs={"wait_for_webhook": True},
                timeout_seconds=5,
            )
        ],
    )

    run_id = "wf_webhook_run_1"

    # Launch workflow task
    task = asyncio.create_task(engine.execute_workflow(workflow, {}, run_id=run_id))

    # Give engine a moment to enter WAITING_WEBHOOK
    await asyncio.sleep(0.05)

    # Deliver webhook callback
    callback_payload = {"status": "dispatched", "external_job_id": 9999}
    delivered = engine.deliver_webhook(run_id, "webhook_step", callback_payload)
    assert delivered is True

    # Await workflow completion
    completed_run = await task
    assert completed_run.status == ExecutionStatus.COMPLETED.value
    assert completed_run.outputs["webhook_step"] == callback_payload
