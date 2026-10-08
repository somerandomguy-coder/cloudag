import asyncio
import json
import os
from typing import Any, Dict, Optional
import httpx

from mcp.server.mcpserver import MCPServer
from cloudag.core.engine import WorkflowEngine
from cloudag.core.graph import CycleDetectedError, InvalidGraphError, WorkflowGraph
from cloudag.models.schema import WorkflowDefinition
from cloudag.storage.database import create_engine_and_sessionmaker, init_db
from cloudag.storage.repository import WorkflowRepository

# Initialize MCP server
mcp_server = MCPServer("cloudag")

# Base URL for remote API server (if configured)
SERVER_URL = os.getenv("CLOUDAG_SERVER_URL", "").rstrip("/")

# In-process engine fallback
_local_engine: Optional[WorkflowEngine] = None
_local_repo: Optional[WorkflowRepository] = None


async def _get_local_engine() -> tuple[WorkflowEngine, WorkflowRepository]:
    global _local_engine, _local_repo
    if _local_engine is None or _local_repo is None:
        db_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///cloudag.db")
        engine_obj, session_factory = create_engine_and_sessionmaker(db_url)
        await init_db(engine_obj)
        _local_repo = WorkflowRepository(session_factory)
        _local_engine = WorkflowEngine(_local_repo)
    return _local_engine, _local_repo


@mcp_server.tool()
async def cloudag_validate_workflow(workflow: Dict[str, Any]) -> Dict[str, Any]:
    """Validates a declarative DAG workflow definition JSON for cycles and dependency validity without executing."""
    try:
        wf = WorkflowDefinition.model_validate(workflow)
        graph = WorkflowGraph(wf)
        topo_order = graph.topological_sort()
        waves = graph.get_execution_waves()
        return {
            "valid": True,
            "workflow_id": wf.workflow_id,
            "step_count": len(wf.steps),
            "topological_order": topo_order,
            "execution_waves": waves,
        }
    except (CycleDetectedError, InvalidGraphError) as e:
        return {"valid": False, "error": str(e), "error_type": type(e).__name__}
    except Exception as e:
        return {"valid": False, "error": str(e)}


@mcp_server.tool()
async def cloudag_register_workflow(workflow: Dict[str, Any]) -> Dict[str, Any]:
    """Registers and stores a declarative DAG workflow definition on cloudag."""
    try:
        wf = WorkflowDefinition.model_validate(workflow)
    except Exception as e:
        return {"success": False, "error": f"Schema validation failed: {str(e)}"}

    if SERVER_URL:
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                res = await client.post(f"{SERVER_URL}/api/v1/workflows", json=workflow)
                return res.json()
            except Exception as e:
                return {"success": False, "error": f"Failed connecting to {SERVER_URL}: {str(e)}"}

    _, repo = await _get_local_engine()
    record = await repo.save_workflow_definition(wf)
    return {
        "success": True,
        "workflow_id": record.workflow_id,
        "version": record.version,
        "message": "Workflow successfully registered locally.",
    }


@mcp_server.tool()
async def cloudag_execute_workflow(
    workflow_id: str,
    inputs: Optional[Dict[str, Any]] = None,
    wait_for_completion: bool = True,
) -> Dict[str, Any]:
    """Executes a previously registered workflow by ID with provided runtime inputs."""
    payload_inputs = inputs or {}

    if SERVER_URL:
        async with httpx.AsyncClient(timeout=300.0) as client:
            try:
                res = await client.post(
                    f"{SERVER_URL}/api/v1/workflows/{workflow_id}/execute",
                    json={"inputs": payload_inputs, "wait_for_completion": wait_for_completion},
                )
                return res.json()
            except Exception as e:
                return {"success": False, "error": f"Failed executing on {SERVER_URL}: {str(e)}"}

    engine, repo = await _get_local_engine()
    wf = await repo.get_workflow_definition(workflow_id)
    if not wf:
        return {"success": False, "error": f"Workflow '{workflow_id}' not found."}

    run = await engine.execute_workflow(wf, payload_inputs)
    return {
        "run_id": run.id,
        "status": run.status,
        "outputs": run.outputs,
        "error_message": run.error_message,
    }


@mcp_server.tool()
async def cloudag_run_workflow_direct(
    workflow: Dict[str, Any],
    inputs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Validates, registers, and executes a full workflow JSON definition in one step. Ideal for AI agents generating workflows."""
    payload_inputs = inputs or {}
    try:
        wf = WorkflowDefinition.model_validate(workflow)
    except Exception as e:
        return {"success": False, "error": f"Schema validation error: {str(e)}"}

    if SERVER_URL:
        async with httpx.AsyncClient(timeout=300.0) as client:
            try:
                # 1. Register
                reg_res = await client.post(f"{SERVER_URL}/api/v1/workflows", json=workflow)
                if reg_res.status_code != 201 and reg_res.status_code != 200:
                    return {"success": False, "error": reg_res.text}

                # 2. Execute
                exec_res = await client.post(
                    f"{SERVER_URL}/api/v1/workflows/{wf.workflow_id}/execute",
                    json={"inputs": payload_inputs, "wait_for_completion": True},
                )
                return exec_res.json()
            except Exception as e:
                return {"success": False, "error": f"Remote execution failed: {str(e)}"}

    engine, repo = await _get_local_engine()
    await repo.save_workflow_definition(wf)
    run = await engine.execute_workflow(wf, payload_inputs)
    return {
        "run_id": run.id,
        "workflow_id": run.workflow_id,
        "status": run.status,
        "outputs": run.outputs,
        "error_message": run.error_message,
    }


@mcp_server.tool()
async def cloudag_get_run_status(run_id: str) -> Dict[str, Any]:
    """Gets detailed execution metrics, timings, and outputs for a given workflow run ID."""
    if SERVER_URL:
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                res = await client.get(f"{SERVER_URL}/api/v1/runs/{run_id}")
                return res.json()
            except Exception as e:
                return {"success": False, "error": f"Failed fetching run: {str(e)}"}

    _, repo = await _get_local_engine()
    run = await repo.get_workflow_run(run_id)
    if not run:
        return {"success": False, "error": f"Run '{run_id}' not found."}

    return {
        "id": run.id,
        "workflow_id": run.workflow_id,
        "status": run.status,
        "inputs": run.inputs,
        "outputs": run.outputs,
        "error_message": run.error_message,
        "step_runs": [
            {
                "step_id": step.step_id,
                "status": step.status,
                "cached": step.cached,
                "duration_ms": step.duration_ms,
                "outputs": step.outputs,
                "error_trace": step.error_trace,
            }
            for step in run.step_runs
        ],
    }


@mcp_server.tool()
async def cloudag_resume_run(run_id: str) -> Dict[str, Any]:
    """Resumes a failed workflow run from its last completed step checkpoint."""
    if SERVER_URL:
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                res = await client.post(f"{SERVER_URL}/api/v1/runs/{run_id}/resume")
                return res.json()
            except Exception as e:
                return {"success": False, "error": f"Failed resuming run: {str(e)}"}

    engine, _ = await _get_local_engine()
    try:
        resumed = await engine.resume_run(run_id)
        return {
            "run_id": resumed.id,
            "status": resumed.status,
            "outputs": resumed.outputs,
            "error_message": resumed.error_message,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp_server.tool()
async def cloudag_send_webhook(run_id: str, step_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Delivers external asynchronous callback data to an active step waiting for a webhook."""
    if SERVER_URL:
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                res = await client.post(
                    f"{SERVER_URL}/api/v1/runs/{run_id}/steps/{step_id}/webhook",
                    json={"payload": payload},
                )
                return res.json()
            except Exception as e:
                return {"success": False, "error": f"Failed delivering webhook: {str(e)}"}

    engine, _ = await _get_local_engine()
    delivered = engine.deliver_webhook(run_id, step_id, payload)
    return {"delivered": delivered, "run_id": run_id, "step_id": step_id}


def main():
    """Runs the MCP server over stdio for AI assistants (Antigravity, Claude Desktop, Cursor)."""
    asyncio.run(mcp_server.run_stdio_async())


if __name__ == "__main__":
    main()
