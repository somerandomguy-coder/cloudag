from typing import Any, Dict
from cloudag.executors.base import BaseExecutor, ExecutionContext
from cloudag.models.schema import StepDefinition


class DataTransformExecutor(BaseExecutor):
    """Handles deterministic data shaping, mapping, filtering, and merging."""

    async def execute(
        self,
        step: StepDefinition,
        resolved_inputs: Dict[str, Any],
        context: ExecutionContext,
    ) -> Any:
        action = step.action.lower()

        if action == "merge":
            result: Dict[str, Any] = {}
            for k, v in resolved_inputs.items():
                if isinstance(v, dict):
                    result.update(v)
                else:
                    result[k] = v
            return result

        if action == "select":
            fields = resolved_inputs.get("fields", [])
            source = resolved_inputs.get("source", {})
            if isinstance(source, dict):
                return {f: source.get(f) for f in fields if f in source}
            return source

        if action == "filter":
            key = resolved_inputs.get("key")
            value = resolved_inputs.get("value")
            items = resolved_inputs.get("items", [])
            if isinstance(items, list) and key:
                return [item for item in items if isinstance(item, dict) and item.get(key) == value]
            return items

        # Default: return resolved_inputs
        return resolved_inputs
