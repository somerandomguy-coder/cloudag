import pytest
from cloudag.mcp_server import (
    cloudag_validate_workflow,
    cloudag_run_workflow_direct,
    cloudag_get_run_status,
)


@pytest.mark.asyncio
async def test_mcp_validation_tool():
    valid_wf = {
        "workflow_id": "mcp_test_wf",
        "steps": [
            {"id": "step_1", "type": "PYTHON_WORKER", "action": "len", "inputs": {"code": "10"}}
        ]
    }
    res = await cloudag_validate_workflow(valid_wf)
    assert res["valid"] is True
    assert res["step_count"] == 1

    cycle_wf = {
        "workflow_id": "mcp_cycle_wf",
        "steps": [
            {"id": "a", "type": "PYTHON_WORKER", "action": "noop", "depends_on": ["b"]},
            {"id": "b", "type": "PYTHON_WORKER", "action": "noop", "depends_on": ["a"]},
        ]
    }
    res_cycle = await cloudag_validate_workflow(cycle_wf)
    assert res_cycle["valid"] is False
    assert "Cycle detected" in res_cycle["error"]


@pytest.mark.asyncio
async def test_mcp_run_direct_and_status():
    wf = {
        "workflow_id": "mcp_exec_wf",
        "steps": [
            {
                "id": "compute",
                "type": "PYTHON_WORKER",
                "action": "calc",
                "inputs": {
                    "val": "${workflow.input.x}",
                    "code": "inputs['val'] * 3",
                },
            }
        ]
    }
    run_res = await cloudag_run_workflow_direct(wf, {"x": 7})
    assert run_res["status"] == "COMPLETED"
    run_id = run_res["run_id"]

    status_res = await cloudag_get_run_status(run_id)
    assert status_res["status"] == "COMPLETED"
    assert status_res["step_runs"][0]["outputs"] == 21
