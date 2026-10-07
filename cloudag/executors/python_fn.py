import asyncio
from datetime import datetime, timezone
import importlib
import inspect
import json
import math
import re
from typing import Any, Callable, Dict, Optional
from cloudag.executors.base import BaseExecutor, ExecutionContext
from cloudag.models.schema import StepDefinition


class PythonFnExecutor(BaseExecutor):
    """Sandboxed local Python worker for deterministic transformations."""

    _registry: Dict[str, Callable] = {}

    @classmethod
    def register(cls, name: str, fn: Callable) -> None:
        """Register a reusable function by name."""
        cls._registry[name] = fn

    @classmethod
    def unregister(cls, name: str) -> None:
        cls._registry.pop(name, None)

    def _resolve_callable(self, action: str) -> Optional[Callable]:
        # 1. Check in-memory registry
        if action in self._registry:
            return self._registry[action]

        # 2. Check dotted import path (e.g., 'pkg.module:function' or 'pkg.module.function')
        if ":" in action:
            mod_name, fn_name = action.split(":", 1)
            try:
                mod = importlib.import_module(mod_name)
                fn = getattr(mod, fn_name)
                if callable(fn):
                    return fn
            except (ImportError, AttributeError):
                pass
        elif "." in action:
            parts = action.rsplit(".", 1)
            try:
                mod = importlib.import_module(parts[0])
                fn = getattr(mod, parts[1])
                if callable(fn):
                    return fn
            except (ImportError, AttributeError):
                pass

        return None

    def _execute_code_sandbox(self, code_str: str, inputs: Dict[str, Any]) -> Any:
        """Executes a Python expression or code snippet in a sandboxed namespace."""
        safe_globals = {
            "math": math,
            "json": json,
            "re": re,
            "datetime": datetime,
            "timezone": timezone,
            "len": len,
            "range": range,
            "int": int,
            "float": float,
            "str": str,
            "bool": bool,
            "list": list,
            "dict": dict,
            "set": set,
            "sorted": sorted,
            "min": min,
            "max": max,
            "sum": sum,
        }
        local_scope = {"inputs": inputs, "params": inputs, "output": None, **inputs}

        # Try evaluating as an expression first
        try:
            return eval(code_str, safe_globals, local_scope)
        except SyntaxError:
            # Execute as a statement block
            exec(code_str, safe_globals, local_scope)
            if "output" in local_scope and local_scope["output"] is not None:
                return local_scope["output"]
            if "result" in local_scope and local_scope["result"] is not None:
                return local_scope["result"]
            return local_scope

    async def execute(
        self,
        step: StepDefinition,
        resolved_inputs: Dict[str, Any],
        context: ExecutionContext,
    ) -> Any:
        fn = self._resolve_callable(step.action)
        if fn:
            sig = inspect.signature(fn)
            params = sig.parameters

            def _invoke_sync() -> Any:
                if len(params) == 0:
                    return fn()
                elif "context" in params and "inputs" in params:
                    return fn(inputs=resolved_inputs, context=context)
                elif "inputs" in params:
                    return fn(inputs=resolved_inputs)
                elif len(params) == 1 and next(iter(params.values())).kind in (
                    inspect.Parameter.POSITIONAL_ONLY,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                ):
                    return fn(resolved_inputs)
                else:
                    call_kwargs = {k: v for k, v in resolved_inputs.items() if k in params}
                    return fn(**call_kwargs)

            try:
                if inspect.iscoroutinefunction(fn):
                    if len(params) == 0:
                        return await fn()
                    elif "context" in params and "inputs" in params:
                        return await fn(inputs=resolved_inputs, context=context)
                    elif "inputs" in params:
                        return await fn(inputs=resolved_inputs)
                    elif len(params) == 1 and next(iter(params.values())).kind in (
                        inspect.Parameter.POSITIONAL_ONLY,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    ):
                        return await fn(resolved_inputs)
                    else:
                        call_kwargs = {k: v for k, v in resolved_inputs.items() if k in params}
                        return await fn(**call_kwargs)
                else:
                    return await asyncio.to_thread(_invoke_sync)
            except Exception as e:
                raise RuntimeError(
                    f"Execution of Python worker function '{step.action}' failed: {str(e)}"
                ) from e

        # If action is code snippet or 'eval'/'code' is provided in inputs
        code_to_run = resolved_inputs.get("code") or step.action
        try:
            return await asyncio.to_thread(self._execute_code_sandbox, code_to_run, resolved_inputs)
        except Exception as e:
            raise RuntimeError(
                f"Python worker execution failed for action '{step.action}': {str(e)}"
            ) from e
