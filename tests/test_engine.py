import asyncio
import time
from typing import Any, Dict
import httpx
import pytest

from cloudag.core.engine import WorkflowEngine
from cloudag.executors.http import HTTPExecutor
from cloudag.executors.llm_agent import LLMAgentExecutor
from cloudag.executors.python_fn import PythonFnExecutor
from cloudag.models.schema import StepDefinition, StepType, WorkflowDefinition
from cloudag.models.state import ExecutionStatus
from cloudag.storage.database import create_engine_and_sessionmaker, init_db
from cloudag.storage.repository import WorkflowRepository


@pytest.fixture
async def setup_engine():
    # Use in-memory SQLite database
    db_url = "sqlite+aiosqlite:///:memory:"
    engine_obj, session_factory = create_engine_and_sessionmaker(db_url)
    await init_db(engine_obj)
    repo = WorkflowRepository(session_factory)

    # Mock HTTP transport for Step 1
    def mock_trends_service(request: httpx.Request) -> httpx.Response:
        time.sleep(0.1)  # 100ms simulated network latency
        return httpx.Response(
            status_code=200,
            json={
                "trends": ["Autonomous Coding", "Multi-Agent Coordination"],
                "volume": 1420,
            },
            headers={"content-type": "application/json"},
        )

    # Python worker for Step 2
    def scrape_news_worker(inputs: Dict[str, Any]) -> Dict[str, Any]:
        time.sleep(0.1)  # 100ms simulated scraper latency
        topic = inputs.get("topic", "Tech")
        return {
            "headlines": [f"New DAG Engine Released for {topic}", "Agentic Systems Advance"],
            "count": 2,
        }

    PythonFnExecutor.register("scrape_news_worker", scrape_news_worker)

    http_executor = HTTPExecutor(mock_handler=mock_trends_service)
    py_executor = PythonFnExecutor()
    llm_executor = LLMAgentExecutor()

    engine = WorkflowEngine(
        repository=repo,
        executors={
            StepType.HTTP_DISPATCH: http_executor,
            StepType.PYTHON_WORKER: py_executor,
            StepType.LLM_AGENT: llm_executor,
        },
    )

    yield engine, repo

    await engine_obj.dispose()


@pytest.mark.asyncio
async def test_hybrid_dag_execution_and_caching(setup_engine):
    engine, repo = setup_engine

    # Define the hybrid workflow matching Section 4 specification
    workflow = WorkflowDefinition(
        workflow_id="hybrid_insights_pipeline",
        version="1.0.0",
        steps=[
            StepDefinition(
                id="step_1",
                type=StepType.HTTP_DISPATCH,
                action="https://api.trends.ai/search",
                inputs={
                    "method": "GET",
                    "topic": "${workflow.input.topic}",
                },
                cache_executed_step=True,
            ),
            StepDefinition(
                id="step_2",
                type=StepType.PYTHON_WORKER,
                action="scrape_news_worker",
                inputs={
                    "topic": "${workflow.input.topic}",
                },
                cache_executed_step=True,
            ),
            StepDefinition(
                id="step_3",
                type=StepType.LLM_AGENT,
                action="mock-llm",
                depends_on=["step_1", "step_2"],
                inputs={
                    "prompt": (
                        "Synthesize trends for ${workflow.input.topic}. "
                        "Trends: ${step_1.output.trends.0}, Volume: ${step_1.output.volume}. "
                        "Top headline: ${step_2.output.headlines.0}."
                    ),
                    "model": "mock-llm",
                },
                cache_executed_step=True,
            ),
        ],
    )

    workflow_input = {"topic": "AI Agents"}

    # --- RUN 1: Cold Execution ---
    t0 = time.perf_counter()
    run_1 = await engine.execute_workflow(workflow, workflow_input)
    total_duration_1 = time.perf_counter() - t0

    assert run_1.status == ExecutionStatus.COMPLETED.value
    assert run_1.outputs is not None

    # Load detailed run records from DB
    persisted_run_1 = await repo.get_workflow_run(run_1.id)
    step_runs_1 = {sr.step_id: sr for sr in persisted_run_1.step_runs}

    sr1 = step_runs_1["step_1"]
    sr2 = step_runs_1["step_2"]
    sr3 = step_runs_1["step_3"]

    # 1. VERIFY CONCURRENCY OF STEPS 1 AND 2
    # Because both steps have a 100ms sleep, sequential execution would take >= 200ms for just steps 1 and 2.
    # Concurrent execution runs them in parallel, so total time for steps 1 and 2 overlaps.
    assert sr1.started_at is not None and sr1.completed_at is not None
    assert sr2.started_at is not None and sr2.completed_at is not None
    # Intervals overlap
    assert sr1.started_at <= sr2.completed_at
    assert sr2.started_at <= sr1.completed_at
    # Total cold run duration is far less than sequential 100ms + 100ms + overhead
    assert total_duration_1 < 0.35, f"Execution took too long: {total_duration_1}s (not running concurrently)"

    # 2. VERIFY STEP 3 FAN-IN BARRIER AND INTERPOLATION
    # Step 3 must start only after BOTH step 1 and step 2 complete
    assert sr3.started_at >= sr1.completed_at
    assert sr3.started_at >= sr2.completed_at
    assert sr3.resolved_inputs["prompt"].startswith("Synthesize trends for AI Agents.")
    assert "Autonomous Coding" in sr3.resolved_inputs["prompt"]
    assert "1420" in sr3.resolved_inputs["prompt"]
    assert "New DAG Engine Released for AI Agents" in sr3.resolved_inputs["prompt"]
    assert sr3.outputs["status"] == "success"

    # None of the steps in Run 1 should be cached
    assert sr1.cached is False
    assert sr2.cached is False
    assert sr3.cached is False

    # --- RUN 2: Warm Execution with cache_executed_step=True ---
    t_cache_0 = time.perf_counter()
    run_2 = await engine.execute_workflow(workflow, workflow_input)
    total_cache_duration = time.perf_counter() - t_cache_0

    assert run_2.status == ExecutionStatus.COMPLETED.value
    persisted_run_2 = await repo.get_workflow_run(run_2.id)
    step_runs_2 = {sr.step_id: sr for sr in persisted_run_2.step_runs}

    # 3. VERIFY CACHE SPEED AND HIT (< 50ms)
    assert total_cache_duration < 0.050, f"Cache run took {total_cache_duration * 1000:.2f}ms, expected < 50ms"

    assert step_runs_2["step_1"].cached is True
    assert step_runs_2["step_2"].cached is True
    assert step_runs_2["step_3"].cached is True

    # Cached outputs must match exactly
    assert step_runs_2["step_1"].outputs == sr1.outputs
    assert step_runs_2["step_2"].outputs == sr2.outputs
    assert step_runs_2["step_3"].outputs == sr3.outputs


@pytest.mark.asyncio
async def test_failure_clean_cancellation(setup_engine):
    engine, repo = setup_engine

    def failing_worker(inputs: Dict[str, Any]) -> None:
        raise ValueError("Simulated worker error in Branch A")

    def slow_worker(inputs: Dict[str, Any]) -> str:
        time.sleep(0.5)
        return "slow_success"

    PythonFnExecutor.register("failing_worker", failing_worker)
    PythonFnExecutor.register("slow_worker", slow_worker)

    workflow = WorkflowDefinition(
        workflow_id="failure_test_wf",
        steps=[
            StepDefinition(
                id="branch_fail",
                type=StepType.PYTHON_WORKER,
                action="failing_worker",
            ),
            StepDefinition(
                id="branch_slow",
                type=StepType.PYTHON_WORKER,
                action="slow_worker",
            ),
            StepDefinition(
                id="join_step",
                type=StepType.PYTHON_WORKER,
                action="slow_worker",
                depends_on=["branch_fail", "branch_slow"],
            ),
        ],
    )

    with pytest.raises(RuntimeError, match="Workflow failed at step 'branch_fail'"):
        await engine.execute_workflow(workflow, {})
