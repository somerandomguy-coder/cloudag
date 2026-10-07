import pytest
from cloudag.core.interpolator import (
    UnresolvedDependencyError,
    VariableInterpolator,
    VariableResolutionError,
)


def test_workflow_input_interpolation():
    workflow_inputs = {
        "topic": "AI Agents",
        "nested": {"param": 100, "flag": True},
    }
    interpolator = VariableInterpolator(workflow_inputs=workflow_inputs)

    assert interpolator.interpolate("${workflow.input.topic}") == "AI Agents"
    assert interpolator.interpolate("${workflow.input.nested.param}") == 100
    assert interpolator.interpolate("${workflow.input.nested.flag}") is True
    assert interpolator.interpolate("${workflow.input}") == workflow_inputs


def test_step_output_deep_path_and_indexing():
    completed_outputs = {
        "step_1": {
            "items": [
                {"title": "Agent Arch", "score": 9.5},
                {"title": "DAG Engines", "score": 8.7},
            ],
            "metadata": {
                "tags": ["python", "ai"],
            },
        }
    }
    interpolator = VariableInterpolator(completed_step_outputs=completed_outputs)

    # Dot indexing
    assert interpolator.interpolate("${step_1.output.items.0.title}") == "Agent Arch"
    assert interpolator.interpolate("${step_1.output.items.1.score}") == 8.7
    assert interpolator.interpolate("${step_1.output.metadata.tags.0}") == "python"

    # Bracket indexing
    assert interpolator.interpolate("${step_1.output.items[0].title}") == "Agent Arch"
    assert interpolator.interpolate("${step_1.output.items[1].score}") == 8.7


def test_type_preservation():
    raw_dict = {"data": [1, 2, 3], "status": "ok"}
    raw_list = ["a", "b", "c"]
    raw_int = 42
    raw_bool = False

    completed_outputs = {
        "producer": {
            "dict_val": raw_dict,
            "list_val": raw_list,
            "int_val": raw_int,
            "bool_val": raw_bool,
        }
    }
    interpolator = VariableInterpolator(completed_step_outputs=completed_outputs)

    res_dict = interpolator.interpolate("${producer.output.dict_val}")
    assert res_dict == raw_dict
    assert isinstance(res_dict, dict)

    res_list = interpolator.interpolate("${producer.output.list_val}")
    assert res_list == raw_list
    assert isinstance(res_list, list)

    res_int = interpolator.interpolate("${producer.output.int_val}")
    assert res_int == 42
    assert isinstance(res_int, int)

    res_bool = interpolator.interpolate("${producer.output.bool_val}")
    assert res_bool is False
    assert isinstance(res_bool, bool)


def test_composite_string_interpolation():
    workflow_inputs = {"topic": "Autonomous Agents"}
    completed_outputs = {
        "step_fetch": {"count": 15, "volume": 1420},
    }
    interpolator = VariableInterpolator(
        workflow_inputs=workflow_inputs,
        completed_step_outputs=completed_outputs,
    )

    template = "Report for ${workflow.input.topic}: count=${step_fetch.output.count}, vol=${step_fetch.output.volume}."
    resolved = interpolator.interpolate(template)
    assert resolved == "Report for Autonomous Agents: count=15, vol=1420."


def test_recursive_nested_structures():
    workflow_inputs = {"env": "prod"}
    completed_outputs = {"step_a": {"id": 123}}
    interpolator = VariableInterpolator(
        workflow_inputs=workflow_inputs,
        completed_step_outputs=completed_outputs,
    )

    input_payload = {
        "static_str": "constant",
        "header": "env: ${workflow.input.env}",
        "nested_dict": {
            "target_id": "${step_a.output.id}",
            "inner_list": ["item", "${workflow.input.env}"],
        },
    }

    resolved = interpolator.interpolate(input_payload)
    assert resolved == {
        "static_str": "constant",
        "header": "env: prod",
        "nested_dict": {
            "target_id": 123,
            "inner_list": ["item", "prod"],
        },
    }


def test_unresolved_dependency_error():
    interpolator = VariableInterpolator(
        completed_step_outputs={"step_1": {"val": 1}},
        known_step_ids={"step_1", "step_2"},
    )
    with pytest.raises(UnresolvedDependencyError, match="has not completed yet"):
        interpolator.interpolate("${step_2.output.val}")


def test_variable_resolution_error_missing_key():
    interpolator = VariableInterpolator(
        workflow_inputs={"user": {"name": "Alice"}},
    )
    with pytest.raises(VariableResolutionError, match="Key 'age' not found"):
        interpolator.interpolate("${workflow.input.user.age}")


def test_variable_resolution_error_index_out_of_range():
    interpolator = VariableInterpolator(
        completed_step_outputs={"step_1": {"items": ["only_one"]}},
    )
    with pytest.raises(VariableResolutionError, match="out of range"):
        interpolator.interpolate("${step_1.output.items.5}")
