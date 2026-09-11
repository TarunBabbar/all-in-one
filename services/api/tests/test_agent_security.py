"""Validate Tool Calls tests.

The input-normalization cases matter more than they look: "Expected path" reads
naturally as a list of tool names, and that shape used to crash the engine with
`'str' object has no attribute 'get'`. A tool that raises on the obvious input is
worse than one that validates nothing, because the failure looks like a bug in
the platform rather than in the payload.
"""

from __future__ import annotations

from app.engines.agent_security import _as_calls, validate_trace


def test_expected_path_accepts_bare_tool_names() -> None:
    """`["search", "open"]` is the natural reading of "expected path"."""
    result = validate_trace(["search", "open_result"], ["search", "open_result"])
    assert result["findings"] == []
    assert result["trust_score"] == 100


def test_expected_path_accepts_objects() -> None:
    result = validate_trace(
        [{"tool": "search"}, {"tool": "open_result"}],
        [{"tool": "search"}, {"tool": "open_result"}],
    )
    assert result["findings"] == []


def test_a_missing_call_is_reported() -> None:
    result = validate_trace(["search", "checkout"], ["search"])
    categories = [f["category"] for f in result["findings"]]
    assert categories == ["missing_tool_call"]
    assert result["trust_score"] < 100


def test_an_unexpected_call_is_reported() -> None:
    result = validate_trace(["search"], ["search", "delete_account"])
    unexpected = [f for f in result["findings"] if f["category"] == "unexpected_tool_call"]
    assert [f["tool"] for f in unexpected] == ["delete_account"]


def test_param_mismatch_is_critical() -> None:
    result = validate_trace(
        [{"tool": "refund", "params": {"amount": 10}}],
        [{"tool": "refund", "params": {"amount": 999}}],
    )
    mismatch = [f for f in result["findings"] if f["category"] == "param_mismatch"]
    assert mismatch and mismatch[0]["severity"] == "critical"


def test_trust_score_never_goes_below_zero() -> None:
    expected = [{"tool": f"t{i}", "params": {"a": i}} for i in range(10)]
    actual = [{"tool": f"t{i}", "params": {"a": 999}} for i in range(10)]
    assert validate_trace(expected, actual)["trust_score"] == 0


def test_malformed_input_is_ignored_rather_than_crashing() -> None:
    """Non-list input and entries without a tool name are dropped."""
    assert _as_calls(None) == []
    assert _as_calls("search") == []
    assert _as_calls([None, 42, "", "  ", {"no_tool": True}]) == []
    assert _as_calls(["  search  ", {"tool": "open"}]) == [
        {"tool": "search"},
        {"tool": "open"},
    ]
