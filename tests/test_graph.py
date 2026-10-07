import pytest
from pydantic import ValidationError
from cloudag.core.graph import CycleDetectedError, InvalidGraphError, WorkflowGraph
from cloudag.models.schema import StepDefinition, StepType, WorkflowDefinition


def create_step(step_id: str, depends_on: list[str] = None) -> StepDefinition:
    return StepDefinition(
        id=step_id,
        type=StepType.PYTHON_WORKER,
        action="test_action",
        depends_on=depends_on or [],
    )


def test_linear_dag():
    steps = [
        create_step("step_1"),
        create_step("step_2", depends_on=["step_1"]),
        create_step("step_3", depends_on=["step_2"]),
    ]
    wf = WorkflowDefinition(workflow_id="linear_wf", steps=steps)
    graph = WorkflowGraph(wf)

    topo = graph.topological_sort()
    assert topo == ["step_1", "step_2", "step_3"]

    waves = graph.get_execution_waves()
    assert waves == [["step_1"], ["step_2"], ["step_3"]]


def test_diamond_dag_fan_out_fan_in():
    steps = [
        create_step("start"),
        create_step("branch_a", depends_on=["start"]),
        create_step("branch_b", depends_on=["start"]),
        create_step("join", depends_on=["branch_a", "branch_b"]),
    ]
    wf = WorkflowDefinition(workflow_id="diamond_wf", steps=steps)
    graph = WorkflowGraph(wf)

    topo = graph.topological_sort()
    assert topo[0] == "start"
    assert topo[-1] == "join"
    assert set(topo[1:3]) == {"branch_a", "branch_b"}

    waves = graph.get_execution_waves()
    assert waves == [["start"], ["branch_a", "branch_b"], ["join"]]


def test_direct_self_cycle_detection():
    steps = [
        create_step("step_1", depends_on=["step_1"]),
    ]
    wf = WorkflowDefinition(workflow_id="self_cycle_wf", steps=steps)
    with pytest.raises(CycleDetectedError, match="depends on itself"):
        WorkflowGraph(wf)


def test_two_node_cycle_detection():
    steps = [
        create_step("step_a", depends_on=["step_b"]),
        create_step("step_b", depends_on=["step_a"]),
    ]
    wf = WorkflowDefinition(workflow_id="cycle_wf_2", steps=steps)
    with pytest.raises(CycleDetectedError, match="Cycle detected"):
        WorkflowGraph(wf)


def test_multi_node_cycle_detection():
    steps = [
        create_step("a", depends_on=["c"]),
        create_step("b", depends_on=["a"]),
        create_step("c", depends_on=["b"]),
        create_step("d", depends_on=["c"]),
    ]
    wf = WorkflowDefinition(workflow_id="cycle_wf_3", steps=steps)
    with pytest.raises(CycleDetectedError, match="Cycle detected"):
        WorkflowGraph(wf)


def test_undefined_dependency_error():
    steps = [
        create_step("step_1", depends_on=["non_existent_step"]),
    ]
    wf = WorkflowDefinition(workflow_id="broken_dep_wf", steps=steps)
    with pytest.raises(InvalidGraphError, match="depends on undefined step"):
        WorkflowGraph(wf)


def test_duplicate_step_id_validation():
    with pytest.raises(ValidationError, match="Duplicate step IDs"):
        WorkflowDefinition(
            workflow_id="dup_wf",
            steps=[
                create_step("step_1"),
                create_step("step_1"),
            ],
        )


def test_multiple_independent_roots():
    steps = [
        create_step("root_1"),
        create_step("root_2"),
        create_step("join", depends_on=["root_1", "root_2"]),
    ]
    wf = WorkflowDefinition(workflow_id="multi_root_wf", steps=steps)
    graph = WorkflowGraph(wf)

    waves = graph.get_execution_waves()
    assert waves == [["root_1", "root_2"], ["join"]]
    assert graph.get_initial_ready_steps() == ["root_1", "root_2"]
