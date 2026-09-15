from collections.abc import Mapping
from typing import Any

import pytest

from avrixo_voice_ops.idempotency import IdempotencyConflict
from avrixo_voice_ops.models import PolicyDecision, ToolInvocationStatus
from avrixo_voice_ops.policy import ContactPolicyProfile
from avrixo_voice_ops.tools import GovernedToolRegistry, ToolDefinition


def profile(*tools: str, approvals: frozenset[str] = frozenset()) -> ContactPolicyProfile:
    return ContactPolicyProfile(
        name="test",
        allowed_tools=frozenset(tools),
        approval_required_tools=approvals,
    )


def test_unlisted_tool_is_denied_fail_closed() -> None:
    registry = GovernedToolRegistry()
    registry.register(ToolDefinition("crm_lookup", "lookup", lambda args: dict(args)))
    result = registry.invoke(
        invocation_id="inv-1",
        session_id="session",
        tool_name="crm_lookup",
        arguments={"id": "1"},
        profile=profile(),
    )
    assert result.policy_decision is PolicyDecision.DENY
    assert result.status is ToolInvocationStatus.DENIED


def test_allowlisted_read_only_tool_executes() -> None:
    registry = GovernedToolRegistry()
    registry.register(ToolDefinition("crm_lookup", "lookup", lambda args: args["id"]))
    result = registry.invoke(
        invocation_id="inv-1",
        session_id="session",
        tool_name="crm_lookup",
        arguments={"id": "contact-1"},
        profile=profile("crm_lookup"),
    )
    assert result.status is ToolInvocationStatus.EXECUTED
    assert result.result == "contact-1"


def test_side_effect_requires_idempotency_key_before_approval() -> None:
    registry = GovernedToolRegistry()
    registry.register(ToolDefinition("crm_update", "update", lambda args: args, side_effect=True))
    result = registry.invoke(
        invocation_id="inv-1",
        session_id="session",
        tool_name="crm_update",
        arguments={"status": "done"},
        profile=profile("crm_update"),
    )
    assert result.status is ToolInvocationStatus.DENIED
    assert "idempotency" in (result.sanitized_error or "")


def test_approved_side_effect_executes_once_and_reuses_result() -> None:
    calls: list[dict[str, Any]] = []

    def update(arguments: Mapping[str, Any]) -> dict[str, bool]:
        calls.append(dict(arguments))
        return {"updated": True}

    registry = GovernedToolRegistry()
    registry.register(
        ToolDefinition(
            "crm_update",
            "update",
            update,
            side_effect=True,
        )
    )
    initial = registry.invoke(
        invocation_id="inv-1",
        session_id="session",
        tool_name="crm_update",
        arguments={"status": "done"},
        profile=profile("crm_update"),
        idempotency_key="idem-1",
    )
    assert initial.status is ToolInvocationStatus.AWAITING_APPROVAL
    assert initial.approval_id is not None
    registry.approvals.resolve(
        initial.approval_id,
        approved=True,
        decided_by="operator-1",
        reason="confirmed",
    )
    first = registry.invoke(
        invocation_id="inv-1",
        session_id="session",
        tool_name="crm_update",
        arguments={"status": "done"},
        profile=profile("crm_update"),
        idempotency_key="idem-1",
        approval_id=initial.approval_id,
    )
    second = registry.invoke(
        invocation_id="inv-1",
        session_id="session",
        tool_name="crm_update",
        arguments={"status": "done"},
        profile=profile("crm_update"),
        idempotency_key="idem-1",
        approval_id=initial.approval_id,
    )
    assert first.status is second.status is ToolInvocationStatus.EXECUTED
    assert len(calls) == 1


def test_rejected_approval_blocks_execution() -> None:
    registry = GovernedToolRegistry()
    registry.register(ToolDefinition("send", "send", lambda args: args, side_effect=True))
    initial = registry.invoke(
        invocation_id="inv-1",
        session_id="session",
        tool_name="send",
        arguments={},
        profile=profile("send"),
        idempotency_key="idem-1",
    )
    assert initial.approval_id is not None
    registry.approvals.resolve(
        initial.approval_id,
        approved=False,
        decided_by="operator-1",
        reason="not authorized",
    )
    result = registry.invoke(
        invocation_id="inv-1",
        session_id="session",
        tool_name="send",
        arguments={},
        profile=profile("send"),
        idempotency_key="idem-1",
        approval_id=initial.approval_id,
    )
    assert result.status is ToolInvocationStatus.REJECTED


def test_idempotency_key_reuse_with_changed_payload_fails() -> None:
    registry = GovernedToolRegistry()
    registry.register(ToolDefinition("lookup", "lookup", lambda args: args))
    registry.invoke(
        invocation_id="inv-1",
        session_id="session",
        tool_name="lookup",
        arguments={"id": "1"},
        profile=profile("lookup"),
        idempotency_key="same-key",
    )
    with pytest.raises(IdempotencyConflict):
        registry.invoke(
            invocation_id="inv-2",
            session_id="session",
            tool_name="lookup",
            arguments={"id": "2"},
            profile=profile("lookup"),
            idempotency_key="same-key",
        )


def test_retries_are_bounded_and_errors_are_redacted() -> None:
    attempts = 0

    def fail(_args: object) -> None:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("password=super-secret")

    registry = GovernedToolRegistry()
    registry.register(ToolDefinition("unstable", "fails", fail, max_attempts=3))
    result = registry.invoke(
        invocation_id="inv-1",
        session_id="session",
        tool_name="unstable",
        arguments={},
        profile=profile("unstable"),
    )
    assert attempts == result.attempts == 3
    assert result.status is ToolInvocationStatus.FAILED
    assert "super-secret" not in (result.sanitized_error or "")


def test_registry_rejects_duplicates_and_unbounded_retries() -> None:
    registry = GovernedToolRegistry()
    registry.register(ToolDefinition("lookup", "lookup", lambda args: args))
    with pytest.raises(ValueError, match="already registered"):
        registry.register(ToolDefinition("lookup", "lookup", lambda args: args))
    with pytest.raises(ValueError, match="between 1 and 3"):
        ToolDefinition("bad", "bad", lambda args: args, max_attempts=4)
