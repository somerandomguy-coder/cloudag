import asyncio
import pytest
from httpx import ASGITransport, AsyncClient

from cloudag.api.server import create_app
from cloudag.executors.python_fn import PythonFnExecutor
from cloudag.storage.database import init_db


@pytest.fixture
async def test_app():
    app = create_app(db_url="sqlite+aiosqlite:///:memory:")
    await init_db(app.state.engine_obj)
    yield app
    await app.state.engine_obj.dispose()


@pytest.mark.asyncio
async def test_api_workflow_lifecycle(test_app):
    def echo_worker(inputs: dict) -> dict:
        return {"echo": inputs.get("val", "")}

    PythonFnExecutor.register("echo_worker", echo_worker)

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Health check
        res = await client.get("/api/v1/health")
        assert res.status_code == 200
        assert res.json()["status"] == "healthy"

        # Register workflow
        wf_payload = {
            "workflow_id": "test_api_wf",
            "version": "1.0.0",
            "steps": [
                {
                    "id": "step_a",
                    "type": "PYTHON_WORKER",
                    "action": "echo_worker",
                    "inputs": {"val": "${workflow.input.msg}"},
                }
            ],
        }
        res_create = await client.post("/api/v1/workflows", json=wf_payload)
        assert res_create.status_code == 201

        # Get workflow
        res_get = await client.get("/api/v1/workflows/test_api_wf")
        assert res_get.status_code == 200
        assert res_get.json()["workflow_id"] == "test_api_wf"

        # Execute workflow with wait_for_completion=True
        exec_payload = {
            "inputs": {"msg": "hello cloudag"},
            "wait_for_completion": True,
        }
        res_exec = await client.post(
            "/api/v1/workflows/test_api_wf/execute", json=exec_payload
        )
        assert res_exec.status_code == 200
        data = res_exec.json()
        assert data["status"] == "COMPLETED"
        assert data["outputs"]["step_a"]["echo"] == "hello cloudag"
        run_id = data["run_id"]

        # Query run status
        res_run = await client.get(f"/api/v1/runs/{run_id}")
        assert res_run.status_code == 200
        run_info = res_run.json()
        assert run_info["status"] == "COMPLETED"
        assert len(run_info["step_runs"]) == 1
        assert run_info["step_runs"][0]["step_id"] == "step_a"


@pytest.mark.asyncio
async def test_api_cycle_rejection(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        wf_cycle_payload = {
            "workflow_id": "cycle_wf",
            "version": "1.0.0",
            "steps": [
                {
                    "id": "step_1",
                    "type": "PYTHON_WORKER",
                    "action": "noop",
                    "depends_on": ["step_2"],
                },
                {
                    "id": "step_2",
                    "type": "PYTHON_WORKER",
                    "action": "noop",
                    "depends_on": ["step_1"],
                },
            ],
        }
        res = await client.post("/api/v1/workflows", json=wf_cycle_payload)
        assert res.status_code == 400
        assert "Cycle detected" in res.json()["detail"]


@pytest.mark.asyncio
async def test_api_webhook_delivery(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        wf_payload = {
            "workflow_id": "webhook_api_wf",
            "version": "1.0.0",
            "steps": [
                {
                    "id": "wait_step",
                    "type": "PYTHON_WORKER",
                    "action": "none",
                    "inputs": {"wait_for_webhook": True},
                    "timeout_seconds": 10,
                }
            ],
        }
        await client.post("/api/v1/workflows", json=wf_payload)

        # Trigger async execution
        exec_res = await client.post(
            "/api/v1/workflows/webhook_api_wf/execute",
            json={"inputs": {}, "wait_for_completion": False},
        )
        assert exec_res.status_code == 200
        run_id = exec_res.json()["run_id"]

        # Wait a moment for the step to wait for webhook
        await asyncio.sleep(0.05)

        # Deliver webhook
        webhook_res = await client.post(
            f"/api/v1/runs/{run_id}/steps/wait_step/webhook",
            json={"payload": {"result": "lambda_done", "status": 200}},
        )
        assert webhook_res.status_code == 200
        assert webhook_res.json()["delivered"] is True

        # Wait for workflow to finish
        await asyncio.sleep(0.05)
        run_res = await client.get(f"/api/v1/runs/{run_id}")
        assert run_res.status_code == 200
        assert run_res.json()["status"] == "COMPLETED"
        assert run_res.json()["outputs"]["wait_step"] == {"result": "lambda_done", "status": 200}


@pytest.mark.asyncio
async def test_api_not_found_handling(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res_wf = await client.get("/api/v1/workflows/does_not_exist")
        assert res_wf.status_code == 404

        res_run = await client.get("/api/v1/runs/does_not_exist")
        assert res_run.status_code == 404


@pytest.mark.asyncio
async def test_api_auth_endpoints(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Check auth status endpoint
        res = await client.get("/api/v1/auth/status")
        assert res.status_code == 200
        data = res.json()
        assert "codex" in data
        assert "gemini" in data
        assert "antigravity" in data

        # Check upload endpoint
        res_upload = await client.post(
            "/api/v1/auth/upload",
            json={"service": "codex", "data": {"auth_mode": "chatgpt"}},
        )
        assert res_upload.status_code == 200
        assert res_upload.json()["status"] == "success"

