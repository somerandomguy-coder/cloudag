import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from cloudag.core.engine import WorkflowEngine
from cloudag.core.graph import CycleDetectedError, InvalidGraphError, WorkflowGraph
from cloudag.models.schema import WorkflowDefinition
from cloudag.models.state import ExecutionStatus
from cloudag.storage.database import (
    create_engine_and_sessionmaker,
    init_db,
    normalize_database_url,
)
from cloudag.storage.repository import WorkflowRepository


class ExecuteRequest(BaseModel):
    inputs: Dict[str, Any] = Field(default_factory=dict)
    run_id: Optional[str] = None
    wait_for_completion: bool = Field(default=False)


class WebhookPayload(BaseModel):
    payload: Any = Field(default_factory=dict)


def create_app(
    db_url: Optional[str] = None,
    engine_instance: Optional[WorkflowEngine] = None,
) -> FastAPI:
    engine_obj, session_factory = create_engine_and_sessionmaker(db_url)
    repository = WorkflowRepository(session_factory)
    orchestration_engine = engine_instance or WorkflowEngine(repository)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await init_db(engine_obj)
        yield
        await engine_obj.dispose()

    app = FastAPI(
        title="cloudag DAG Workflow Engine",
        version="0.1.0",
        description="Declarative JSON DAG Workflow Engine with parallel execution, checkpointing, and LLM steps.",
        lifespan=lifespan,
    )

    # Attach to app state for access
    app.state.repository = repository
    app.state.engine = orchestration_engine
    app.state.engine_obj = engine_obj

    @app.get("/api/v1/health")
    async def health_check():
        return {"status": "healthy", "service": "cloudag"}

    from fastapi.responses import HTMLResponse
    from cloudag.api.ui import HTML_PAGE

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    @app.get("/ui", response_class=HTMLResponse, include_in_schema=False)
    async def studio_ui():
        return HTML_PAGE

    @app.post(
        "/api/v1/workflows",
        status_code=status.HTTP_201_CREATED,
        summary="Register and validate a new workflow definition",
    )
    async def register_workflow(workflow: WorkflowDefinition):
        try:
            # Validate DAG structure and cycles
            WorkflowGraph(workflow)
        except (CycleDetectedError, InvalidGraphError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid workflow graph: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Validation failed: {str(e)}",
            )

        record = await repository.save_workflow_definition(workflow)
        return {
            "workflow_id": record.workflow_id,
            "version": record.version,
            "message": "Workflow successfully registered and validated.",
        }

    @app.get("/api/v1/workflows/{workflow_id}")
    async def get_workflow(workflow_id: str):
        wf = await repository.get_workflow_definition(workflow_id)
        if not wf:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workflow '{workflow_id}' not found.",
            )
        return wf

    @app.post("/api/v1/workflows/{workflow_id}/execute")
    async def execute_workflow(
        workflow_id: str,
        request: ExecuteRequest,
    ):
        wf = await repository.get_workflow_definition(workflow_id)
        if not wf:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workflow '{workflow_id}' not found.",
            )

        if request.wait_for_completion:
            try:
                run = await orchestration_engine.execute_workflow(
                    workflow=wf,
                    inputs=request.inputs,
                    run_id=request.run_id,
                )
                return {
                    "run_id": run.id,
                    "status": run.status,
                    "outputs": run.outputs,
                    "error_message": run.error_message,
                }
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Workflow execution failed: {str(e)}",
                )
        else:
            # Asynchronous background execution
            import uuid
            run_id = request.run_id or str(uuid.uuid4())
            asyncio.create_task(
                orchestration_engine.execute_workflow(
                    workflow=wf,
                    inputs=request.inputs,
                    run_id=run_id,
                )
            )
            return {
                "run_id": run_id,
                "status": ExecutionStatus.RUNNING.value,
                "message": "Workflow execution scheduled.",
            }

    @app.get("/api/v1/runs/{run_id}")
    async def get_run(run_id: str):
        run = await repository.get_workflow_run(run_id)
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run '{run_id}' not found.",
            )

        return {
            "id": run.id,
            "workflow_id": run.workflow_id,
            "status": run.status,
            "inputs": run.inputs,
            "outputs": run.outputs,
            "error_message": run.error_message,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "step_runs": [
                {
                    "id": step.id,
                    "step_id": step.step_id,
                    "status": step.status,
                    "input_hash": step.input_hash,
                    "raw_inputs": step.raw_inputs,
                    "resolved_inputs": step.resolved_inputs,
                    "outputs": step.outputs,
                    "error_trace": step.error_trace,
                    "duration_ms": step.duration_ms,
                    "cached": step.cached,
                    "started_at": step.started_at.isoformat() if step.started_at else None,
                    "completed_at": step.completed_at.isoformat() if step.completed_at else None,
                }
                for step in run.step_runs
            ],
        }

    @app.post("/api/v1/runs/{run_id}/resume")
    async def resume_run(run_id: str):
        run = await repository.get_workflow_run(run_id)
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run '{run_id}' not found.",
            )

        try:
            resumed_run = await orchestration_engine.resume_run(run_id)
            return {
                "run_id": resumed_run.id,
                "status": resumed_run.status,
                "outputs": resumed_run.outputs,
                "error_message": resumed_run.error_message,
            }
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to resume run: {str(e)}",
            )

    @app.post("/api/v1/runs/{run_id}/steps/{step_id}/webhook")
    async def deliver_webhook(
        run_id: str,
        step_id: str,
        body: WebhookPayload,
    ):
        delivered = orchestration_engine.deliver_webhook(
            run_id=run_id,
            step_id=step_id,
            payload=body.payload,
        )
        if not delivered:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No active waiting step '{step_id}' found for run '{run_id}'.",
            )

        return {
            "delivered": True,
            "run_id": run_id,
            "step_id": step_id,
            "message": "Webhook payload successfully dispatched to step.",
        }

    @app.get("/api/v1/auth/status")
    async def get_auth_status():
        import shutil
        from pathlib import Path
        home = Path.home()
        codex_auth = (home / ".codex" / "auth.json").exists()
        gemini_auth = (home / ".gemini" / "google_accounts.json").exists()

        return {
            "codex": {
                "installed": bool(shutil.which("codex")),
                "authenticated": codex_auth,
                "config_dir": str(home / ".codex"),
            },
            "gemini": {
                "installed": bool(shutil.which("gemini")),
                "authenticated": gemini_auth,
                "config_dir": str(home / ".gemini"),
            },
            "antigravity": {
                "installed": bool(shutil.which("agy") or shutil.which("gemini")),
                "binary": "agy" if shutil.which("agy") else ("gemini" if shutil.which("gemini") else None),
                "authenticated": gemini_auth,
            },
            "claude": {
                "installed": bool(shutil.which("claude")),
                "api_key_configured": bool(os.getenv("ANTHROPIC_API_KEY")),
            },
            "openai_api_key": bool(os.getenv("OPENAI_API_KEY")),
            "gemini_api_key": bool(os.getenv("GEMINI_API_KEY")),
        }

    @app.post("/api/v1/auth/upload")
    async def upload_auth(body: Dict[str, Any]):
        """Upload credentials JSON for codex or gemini/antigravity directly."""
        import json
        from pathlib import Path

        service = body.get("service")
        data = body.get("data")
        if not service or not data:
            raise HTTPException(status_code=400, detail="Must provide 'service' and 'data'")

        home = Path.home()
        if service in ("codex", "chatgpt"):
            target_dir = home / ".codex"
            target_dir.mkdir(parents=True, exist_ok=True)
            target_file = target_dir / "auth.json"
            target_file.write_text(json.dumps(data, indent=2))
            return {"status": "success", "message": f"Successfully updated {target_file}"}
        elif service in ("gemini", "antigravity"):
            target_dir = home / ".gemini"
            target_dir.mkdir(parents=True, exist_ok=True)
            target_file = target_dir / "google_accounts.json"
            target_file.write_text(json.dumps(data, indent=2))
            return {"status": "success", "message": f"Successfully updated {target_file}"}
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported service '{service}'")

    return app


app = create_app()
