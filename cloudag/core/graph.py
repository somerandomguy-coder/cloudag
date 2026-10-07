from collections import defaultdict, deque
from typing import Dict, List, Set
from cloudag.models.schema import StepDefinition, WorkflowDefinition


class CycleDetectedError(Exception):
    """Raised when a cycle is detected in the DAG dependency graph."""
    pass


class InvalidGraphError(Exception):
    """Raised when the workflow graph contains invalid references or malformed structure."""
    pass


class WorkflowGraph:
    """Validates DAG structure, detects cycles, and calculates execution ordering."""

    def __init__(self, workflow: WorkflowDefinition):
        self.workflow = workflow
        self.steps_map: Dict[str, StepDefinition] = {step.id: step for step in workflow.steps}
        # Adjacency lists:
        # direct_deps[u] = set of steps u depends on (incoming edges)
        # dependents[u] = set of steps that depend on u (outgoing edges)
        self.direct_deps: Dict[str, Set[str]] = defaultdict(set)
        self.dependents: Dict[str, Set[str]] = defaultdict(set)
        self._build_graph()
        self.validate()

    def _build_graph(self) -> None:
        for step in self.workflow.steps:
            for dep in step.depends_on:
                self.direct_deps[step.id].add(dep)
                self.dependents[dep].add(step.id)

    def validate(self) -> None:
        """Validates that all dependencies exist and no cycles exist."""
        # 1. Check for missing dependencies
        for step_id, deps in self.direct_deps.items():
            for dep in deps:
                if dep not in self.steps_map:
                    raise InvalidGraphError(
                        f"Step '{step_id}' depends on undefined step '{dep}'."
                    )
                if dep == step_id:
                    raise CycleDetectedError(
                        f"Step '{step_id}' directly depends on itself (cycle: {step_id} -> {step_id})."
                    )

        # 2. Cycle detection via DFS with 3-state coloring
        # 0: UNVISITED, 1: VISITING, 2: VISITED
        state: Dict[str, int] = {s_id: 0 for s_id in self.steps_map}
        parent: Dict[str, str] = {}

        def dfs(node: str, path: List[str]) -> None:
            state[node] = 1  # visiting
            path.append(node)

            # Follow outgoing edges: node -> dependent
            for next_node in sorted(self.dependents.get(node, set())):
                if state[next_node] == 1:
                    # Found cycle
                    cycle_start_idx = path.index(next_node)
                    cycle_nodes = path[cycle_start_idx:] + [next_node]
                    cycle_str = " -> ".join(cycle_nodes)
                    raise CycleDetectedError(f"Cycle detected in workflow graph: {cycle_str}")
                elif state[next_node] == 0:
                    parent[next_node] = node
                    dfs(next_node, path)

            path.pop()
            state[node] = 2  # visited

        for step_id in sorted(self.steps_map.keys()):
            if state[step_id] == 0:
                dfs(step_id, [])

    def topological_sort(self) -> List[str]:
        """Calculates a valid topological sort using Kahn's algorithm."""
        in_degree: Dict[str, int] = {s_id: len(self.direct_deps[s_id]) for s_id in self.steps_map}
        queue: deque[str] = deque(sorted([s_id for s_id, deg in in_degree.items() if deg == 0]))
        sorted_order: List[str] = []

        while queue:
            curr = queue.popleft()
            sorted_order.append(curr)

            for dependent in sorted(self.dependents[curr]):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(sorted_order) != len(self.steps_map):
            raise CycleDetectedError("Cycle detected during topological sorting.")

        return sorted_order

    def get_execution_waves(self) -> List[List[str]]:
        """Groups steps into execution waves where all steps in a wave can execute concurrently."""
        in_degree: Dict[str, int] = {s_id: len(self.direct_deps[s_id]) for s_id in self.steps_map}
        current_wave = sorted([s_id for s_id, deg in in_degree.items() if deg == 0])
        waves: List[List[str]] = []

        visited_count = 0
        while current_wave:
            waves.append(current_wave)
            visited_count += len(current_wave)
            next_wave_candidates: Set[str] = set()

            for node in current_wave:
                for dependent in self.dependents[node]:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        next_wave_candidates.add(dependent)

            current_wave = sorted(list(next_wave_candidates))

        if visited_count != len(self.steps_map):
            raise CycleDetectedError("Cycle detected while computing execution waves.")

        return waves

    def get_dependencies(self, step_id: str) -> Set[str]:
        return set(self.direct_deps.get(step_id, set()))

    def get_dependents(self, step_id: str) -> Set[str]:
        return set(self.dependents.get(step_id, set()))

    def get_initial_ready_steps(self) -> List[str]:
        return sorted([step_id for step_id, deps in self.direct_deps.items() if len(deps) == 0])
