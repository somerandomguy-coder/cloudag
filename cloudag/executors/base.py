from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from cloudag.models.schema import StepDefinition


class ExecutionContext:
    """Execution metadata passed to executors during step evaluation."""

    def __init__(
        self,
        run_id: str,
        workflow_id: str,
        step_id: str,
        extra: Optional[Dict[str, Any]] = None,
    ):
        self.run_id = run_id
        self.workflow_id = workflow_id
        self.step_id = step_id
        self.extra = extra or {}


class BaseExecutor(ABC):
    """Abstract interface for all step executors."""

    @abstractmethod
    async def execute(
        self,
        step: StepDefinition,
        resolved_inputs: Dict[str, Any],
        context: ExecutionContext,
    ) -> Any:
        """Executes a step with resolved inputs and returns the step output."""
        pass
