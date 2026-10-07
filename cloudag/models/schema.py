from enum import Enum
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class StepType(str, Enum):
    HTTP_DISPATCH = "HTTP_DISPATCH"
    PYTHON_WORKER = "PYTHON_WORKER"
    LLM_AGENT = "LLM_AGENT"
    DATA_TRANSFORM = "DATA_TRANSFORM"


class RetryPolicy(BaseModel):
    max_retries: int = Field(default=0, ge=0, description="Maximum retry attempts on failure")
    backoff_factor: float = Field(default=1.0, ge=0.0, description="Exponential backoff multiplier")


class StepDefinition(BaseModel):
    id: str = Field(..., description="Unique step identifier (alphanumeric snake_case)")
    type: StepType = Field(..., description="Execution type of the step")
    depends_on: List[str] = Field(default_factory=list, description="IDs of upstream steps")
    action: str = Field(..., description="Handler name, URL, or function identifier")
    inputs: Dict[str, Any] = Field(default_factory=dict, description="Static inputs or template strings")
    cache_executed_step: bool = Field(default=False, description="Reuse cached successful execution by input hash")
    retry_policy: Optional[RetryPolicy] = Field(default=None, description="Optional retry configuration")
    timeout_seconds: int = Field(default=300, gt=0, description="Step execution timeout in seconds")

    @field_validator("id")
    @classmethod
    def validate_id_format(cls, value: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_]+$", value):
            raise ValueError(f"Step ID '{value}' must be alphanumeric snake_case ([a-zA-Z0-9_]+)")
        return value


class WorkflowDefinition(BaseModel):
    workflow_id: str = Field(..., description="Unique workflow identifier")
    version: str = Field(default="1.0.0", description="Semantic workflow version")
    trigger: Dict[str, Any] = Field(
        default_factory=lambda: {"type": "manual"},
        description="Trigger metadata (webhook, cron, manual)",
    )
    input_schema: Dict[str, Any] = Field(
        default_factory=dict,
        description="Expected workflow input schema definition",
    )
    steps: List[StepDefinition] = Field(..., description="Ordered or unordered list of DAG step definitions")

    @model_validator(mode="after")
    def validate_unique_step_ids(self) -> "WorkflowDefinition":
        seen_ids = set()
        duplicates = []
        for step in self.steps:
            if step.id in seen_ids:
                duplicates.append(step.id)
            seen_ids.add(step.id)
        if duplicates:
            raise ValueError(f"Duplicate step IDs found in workflow: {duplicates}")
        return self

    def get_step(self, step_id: str) -> Optional[StepDefinition]:
        for step in self.steps:
            if step.id == step_id:
                return step
        return None
