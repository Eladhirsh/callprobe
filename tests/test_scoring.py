import json
from pathlib import Path

import pytest

from callprobe.client import parse_completion
from callprobe.loader import load_suite
from callprobe.runner import build_toolset
from callprobe.scoring import score

SUITE = Path(__file__).resolve().parents[1] / "src" / "callprobe" / "suites" / "core"


@pytest.fixture(scope="module")
def suite():
    return load_suite(SUITE)


def body_with_call(name, arguments, as_dict=False):
    return {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": arguments
                                if as_dict
                                else json.dumps(arguments),
                            },
                        }
                    ]
                }
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20},
    }


def body_no_call(text="Sure, could you tell me the order number?"):
    return {
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 12},
    }


def run(suite, task_id, body, pad=0):
    task = next(t for t in suite.tasks if t.id == task_id)
    bundle, _ = build_toolset(suite, task, pad, seed=0)
    completion = parse_completion(body, 12.5)
    return score(task, bundle, completion, model="stub", pad=pad, repeat=0)


def test_suite_loads(suite):
    assert len(suite.tasks) >= 12
    assert "support" in suite.bundles
    assert len(suite.distractors) >= 12


def test_suite_has_version_and_hash(suite):
    assert suite.name == "core"
    assert suite.version == 2
    assert len(suite.hash) == 16  # truncated sha256 hex digest
    assert suite.hash == load_suite(SUITE).hash  # deterministic


def test_correct_call_passes(suite):
    result = run(suite, "select-status-direct", body_with_call(
        "get_order_status", {"order_id": "ORD-448120"}))
    assert result.success
    assert result.selection_ok and result.schema_ok and result.args_ok


def test_wrong_tool_fails_selection_only(suite):
    result = run(suite, "select-status-direct", body_with_call(
        "search_orders", {"email": "a@b.com"}))
    assert not result.selection_ok
    assert result.schema_ok  # the call it made was itself well formed
    assert not result.success


def test_schema_violation_is_caught(suite):
    result = run(suite, "select-status-direct", body_with_call(
        "get_order_status", {"order_id": "448120"}))
    assert result.selection_ok
    assert not result.schema_ok
    assert any("schema" in f for f in result.failures)


def test_valid_schema_wrong_value_is_caught(suite):
    """The failure this whole tool exists to surface."""
    result = run(suite, "args-partial-refund", body_with_call(
        "issue_refund",
        {"order_id": "ORD-991003", "reason": "damaged", "amount_cents": 8450},
    ))
    assert result.selection_ok
    assert result.schema_ok
    assert not result.args_ok
    assert not result.success


def test_partial_refund_correct(suite):
    result = run(suite, "args-partial-refund", body_with_call(
        "issue_refund",
        {"order_id": "ORD-991003", "reason": "damaged", "amount_cents": 4225},
    ))
    assert result.success


def test_nested_argument_checks(suite):
    result = run(suite, "args-nested-address", body_with_call(
        "update_shipping_address",
        {
            "order_id": "ORD-772341",
            "address": {
                "line1": "55 Riverside Drive",
                "line2": "Apt 12B",
                "city": "New York",
                "postal_code": "10024",
                "country": "US",
            },
        },
    ))
    assert result.success


def test_abstention_rewarded(suite):
    result = run(suite, "abstain-missing-identifier", body_no_call())
    assert result.success


def test_hallucinated_call_on_abstention_fails(suite):
    result = run(suite, "abstain-missing-identifier", body_with_call(
        "issue_refund", {"order_id": "ORD-000001", "reason": "damaged"}))
    assert not result.success
    assert "when no tool applied" in result.failures[0]


def test_missing_call_fails(suite):
    result = run(suite, "select-status-direct", body_no_call())
    assert not result.success
    assert result.failures == ["no tool call produced"]


def test_arguments_returned_as_object(suite):
    """Some servers return arguments already decoded. Both must work."""
    result = run(suite, "select-status-direct", body_with_call(
        "get_order_status", {"order_id": "ORD-448120"}, as_dict=True))
    assert result.success


def test_unparseable_arguments(suite):
    body = body_with_call("get_order_status", {})
    body["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = "{oops"
    result = run(suite, "select-status-direct", body)
    assert not result.success
    assert any("did not parse" in f for f in result.failures)


def test_padding_adds_distractors_without_removing_real_tools(suite):
    task = next(t for t in suite.tasks if t.id == "select-status-direct")
    bundle, payload = build_toolset(suite, task, pad=8, seed=1)
    names = {t.name for t in bundle.tools}
    assert "get_order_status" in names
    assert len(payload) == len(suite.bundles["support"].tools) + 8


def test_suite_validates(suite):
    """A typo in an expectation silently fails every model. Catch it here.

    Also checks that asserted values are themselves legal for the schema.
    """
    from callprobe.validate import validate_suite

    problems = validate_suite(suite)
    assert not problems, problems


def test_every_category_has_tasks(suite):
    categories = {t.category for t in suite.tasks}
    assert categories == {"select", "abstain", "args", "depth", "sequence"}


def test_stringified_arguments_fail_strict_but_pass_lenient(suite):
    """llama3.1 returns every value as a string. Right answer, unusable call."""
    result = run(suite, "args-partial-refund", body_with_call(
        "issue_refund",
        {"order_id": "ORD-991003", "reason": "damaged", "amount_cents": "4225"},
    ))
    assert not result.success
    assert not result.schema_ok
    assert result.success_lenient
    assert result.type_coerced


def test_wrong_value_is_not_rescued_by_coercion(suite):
    # Coercion fixes types, never values.
    result = run(suite, "args-partial-refund", body_with_call(
        "issue_refund",
        {"order_id": "ORD-991003", "reason": "damaged", "amount_cents": "8450"},
    ))
    assert not result.success
    assert not result.success_lenient


@pytest.mark.parametrize("extra_first", [False, True])
@pytest.mark.parametrize("amount", [4225, "4225"])
def test_extra_calls_never_pass_even_with_correct_or_coercible_call(suite, extra_first, amount):
    body = body_with_call("issue_refund", {
        "order_id": "ORD-991003", "reason": "damaged", "amount_cents": amount,
    })
    calls = body["choices"][0]["message"]["tool_calls"]
    extra = body_with_call("get_order_status", {"order_id": "ORD-991003"})
    calls.insert(0 if extra_first else 1, extra["choices"][0]["message"]["tool_calls"][0])
    result = run(suite, "args-partial-refund", body)
    assert result.selection_ok
    assert not result.call_count_ok
    assert not result.success and not result.success_lenient
    assert len(result.calls) == 2


@pytest.mark.parametrize("task_id,body", [
    ("abstain-missing-identifier", body_no_call()),
    ("select-status-direct", body_with_call("get_order_status", {"order_id": "ORD-448120"})),
])
def test_truncated_responses_do_not_pass(suite, task_id, body):
    body["choices"][0]["finish_reason"] = "length"
    result = run(suite, task_id, body)
    assert result.truncated
    assert not result.success and not result.success_lenient
    assert any("truncated" in failure for failure in result.failures)


def test_call_evidence_survives_json_roundtrip(suite):
    from callprobe.models import TaskResult

    body = body_with_call("get_order_status", {})
    call = body["choices"][0]["message"]["tool_calls"][0]
    call["id"] = "call_123"
    call["function"]["arguments"] = '{"order_id":'
    body["choices"][0]["finish_reason"] = "tool_calls"
    result = TaskResult.model_validate_json(run(suite, "select-status-direct", body).model_dump_json())
    assert result.calls[0].id == "call_123"
    assert result.calls[0].raw_arguments == '{"order_id":'
    assert result.calls[0].parse_error
    assert result.finish_reason == "tool_calls"


@pytest.mark.parametrize("values,index", [([], -1), ([1], -2), ([1], -99999), ([1], 1)])
def test_out_of_range_argument_path_returns_missing_instead_of_crashing(values, index):
    from callprobe.scoring import MISSING, resolve, apply_check
    from callprobe.models import ArgCheck
    arguments = {"items": values}
    path = f"items.{index}"
    assert resolve(arguments, path) is MISSING
    passed, message = apply_check(arguments, ArgCheck(path=path, op="eq", value=1))
    assert passed is False
    assert "missing" in message
