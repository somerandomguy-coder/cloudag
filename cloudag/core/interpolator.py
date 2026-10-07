from collections.abc import Mapping, Sequence
import re
from typing import Any, Dict, List, Optional, Set


class UnresolvedDependencyError(Exception):
    """Raised when an interpolation target references an uncompleted step or missing output."""
    pass


class VariableResolutionError(Exception):
    """Raised when a path cannot be found or an expression is invalid."""
    pass


class VariableInterpolator:
    """Recursively interpolates ${workflow.input.<path>} and ${<step_id>.output.<path>} expressions."""

    # Matches ${source.kind.path} or ${source.kind}
    EXPR_PATTERN = re.compile(r"\$\{([a-zA-Z0-9_]+)\.(input|output)(?:\.([a-zA-Z0-9_\[\].\-]+))?\}")
    STRICT_PATTERN = re.compile(r"^\$\{([a-zA-Z0-9_]+)\.(input|output)(?:\.([a-zA-Z0-9_\[\].\-]+))?\}$")

    def __init__(
        self,
        workflow_inputs: Optional[Dict[str, Any]] = None,
        completed_step_outputs: Optional[Dict[str, Any]] = None,
        known_step_ids: Optional[Set[str]] = None,
    ):
        self.workflow_inputs = workflow_inputs or {}
        self.completed_step_outputs = completed_step_outputs or {}
        self.known_step_ids = known_step_ids or set(self.completed_step_outputs.keys())

    def _extract_deep_path(self, target: Any, path: Optional[str]) -> Any:
        if not path:
            return target

        # Normalize bracket notation e.g., items[0] or ['key'] -> items.0 or .key
        normalized = re.sub(r"\[['\"]?([^'\"\]]+)['\"]?\]", r".\1", path)
        segments = [s for s in normalized.split(".") if s]

        curr = target
        for seg in segments:
            if curr is None:
                raise VariableResolutionError(f"Cannot access path segment '{seg}' on None object in '{path}'.")

            if isinstance(curr, Mapping):
                if seg in curr:
                    curr = curr[seg]
                elif seg.isdigit() and int(seg) in curr:
                    curr = curr[int(seg)]
                else:
                    raise VariableResolutionError(
                        f"Key '{seg}' not found in dictionary. Available keys: {list(curr.keys())}."
                    )
            elif isinstance(curr, Sequence) and not isinstance(curr, (str, bytes)):
                if not seg.isdigit():
                    raise VariableResolutionError(
                        f"Cannot index sequence with non-numeric segment '{seg}' in path '{path}'."
                    )
                idx = int(seg)
                if idx < 0 or idx >= len(curr):
                    raise VariableResolutionError(
                        f"Index {idx} out of range for sequence of length {len(curr)} in path '{path}'."
                    )
                curr = curr[idx]
            elif hasattr(curr, seg):
                curr = getattr(curr, seg)
            else:
                raise VariableResolutionError(
                    f"Attribute or key '{seg}' not found on object of type {type(curr).__name__}."
                )

        return curr

    def _resolve_expr(self, source_name: str, source_kind: str, path: Optional[str]) -> Any:
        if source_name == "workflow":
            if source_kind != "input":
                raise VariableResolutionError(
                    f"Invalid workflow reference '${{workflow.{source_kind}}}'. Only '${{workflow.input}}' is supported."
                )
            return self._extract_deep_path(self.workflow_inputs, path)

        # Step reference
        if source_name not in self.completed_step_outputs:
            if source_name in self.known_step_ids:
                raise UnresolvedDependencyError(
                    f"Step '{source_name}' has not completed yet or its output is not available."
                )
            else:
                raise UnresolvedDependencyError(
                    f"Step '{source_name}' is not recognized or not completed."
                )

        if source_kind != "output":
            raise VariableResolutionError(
                f"Invalid step reference '${{{source_name}.{source_kind}}}'. Only '${{{source_name}.output}}' is supported."
            )

        step_output = self.completed_step_outputs[source_name]
        return self._extract_deep_path(step_output, path)

    def interpolate_string(self, text: str) -> Any:
        stripped = text.strip()
        strict_match = self.STRICT_PATTERN.fullmatch(stripped)
        if strict_match:
            # Type preservation: resolve to raw object
            source_name, source_kind, path = strict_match.groups()
            return self._resolve_expr(source_name, source_kind, path)

        # Composite string: replace all occurrences
        def replacer(match: re.Match) -> str:
            source_name, source_kind, path = match.groups()
            resolved = self._resolve_expr(source_name, source_kind, path)
            return str(resolved)

        return self.EXPR_PATTERN.sub(replacer, text)

    def interpolate(self, value: Any) -> Any:
        """Recursively resolves all template expressions in dicts, lists, and strings."""
        if isinstance(value, str):
            return self.interpolate_string(value)
        elif isinstance(value, dict):
            return {k: self.interpolate(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self.interpolate(item) for item in value]
        elif isinstance(value, tuple):
            return tuple(self.interpolate(item) for item in value)
        else:
            return value
