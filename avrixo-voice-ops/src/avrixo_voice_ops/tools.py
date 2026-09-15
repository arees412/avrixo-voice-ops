"""Governed tool registry with policy, approval, retries, and idempotency."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .approvals import ApprovalGate
from .idempotency import IdempotencyStatus, IdempotencyStore
from .models import (
    ApprovalStatus,
    PolicyDecision,
    ToolInvocation,
    ToolInvocationStatus,
    utc_now,
)
from .policy import ContactPolicyProfile
from .redaction import TranscriptRedactor

ToolHandler = Callable[[Mapping[str, Any]], Any]


@dataclass(slots=True, frozen=True)
class ToolDefinition:
    name: str
    description: str
    handler: ToolHandler
    side_effect: bool = False
    approval_required: bool = False
    max_attempts: int = 1

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("tool name cannot be empty")
        if not 1 <= self.max_attempts <= 3:
            raise ValueError("tool max_attempts must be between 1 and 3")


class ToolPolicyEngine:
    """Fail-closed tool policy; side effects always require approval."""

    @staticmethod
    def decide(profile: ContactPolicyProfile, tool: ToolDefinition) -> PolicyDecision:
        if tool.name in profile.restricted_tools:
            return PolicyDecision.DENY
        if tool.name not in profile.allowed_tools:
            return PolicyDecision.DENY
        if (
            tool.side_effect
            or tool.approval_required
            or tool.name in profile.approval_required_tools
        ):
            return PolicyDecision.REQUIRES_APPROVAL
        return PolicyDecision.ALLOW


class GovernedToolRegistry:
    def __init__(
        self,
        *,
        approvals: ApprovalGate | None = None,
        idempotency: IdempotencyStore | None = None,
        redactor: TranscriptRedactor | None = None,
    ) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self.approvals = approvals or ApprovalGate()
        self.idempotency = idempotency or IdempotencyStore()
        self.redactor = redactor or TranscriptRedactor()

    def register(self, tool: ToolDefinition) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    def get(self, name: str) -> ToolDefinition:
        try:
            return self._tools[name]
        except KeyError as error:
            raise KeyError(f"unknown tool: {name}") from error

    def invoke(
        self,
        *,
        invocation_id: str,
        session_id: str,
        tool_name: str,
        arguments: Mapping[str, Any],
        profile: ContactPolicyProfile,
        idempotency_key: str | None = None,
        approval_id: str | None = None,
    ) -> ToolInvocation:
        tool = self.get(tool_name)
        decision = ToolPolicyEngine.decide(profile, tool)
        invocation = ToolInvocation(
            id=invocation_id,
            session_id=session_id,
            tool_name=tool_name,
            arguments_summary=self.redactor.redact_value(dict(arguments)),
            policy_decision=decision,
            status=ToolInvocationStatus.PENDING,
            idempotency_key=idempotency_key,
        )
        if decision is PolicyDecision.DENY:
            invocation.status = ToolInvocationStatus.DENIED
            invocation.completed_at = utc_now()
            return invocation

        if tool.side_effect and not idempotency_key:
            invocation.status = ToolInvocationStatus.DENIED
            invocation.sanitized_error = "side effects require an idempotency key"
            invocation.completed_at = utc_now()
            return invocation

        if decision is PolicyDecision.REQUIRES_APPROVAL:
            if approval_id is None:
                approval = self.approvals.request(
                    session_id=session_id,
                    tool_invocation_id=invocation_id,
                )
                invocation.approval_id = approval.id
                invocation.status = ToolInvocationStatus.AWAITING_APPROVAL
                return invocation
            approval = self.approvals.get(approval_id)
            invocation.approval_id = approval.id
            if approval.tool_invocation_id != invocation_id or approval.session_id != session_id:
                invocation.status = ToolInvocationStatus.DENIED
                invocation.sanitized_error = "approval scope mismatch"
                invocation.completed_at = utc_now()
                return invocation
            if approval.status is not ApprovalStatus.APPROVED:
                invocation.status = (
                    ToolInvocationStatus.REJECTED
                    if approval.status is ApprovalStatus.REJECTED
                    else ToolInvocationStatus.AWAITING_APPROVAL
                )
                return invocation

        if idempotency_key is not None:
            record, claimed = self.idempotency.claim(
                idempotency_key,
                {"tool": tool_name, "arguments": dict(arguments)},
            )
            if not claimed:
                if record.status is IdempotencyStatus.COMPLETED:
                    invocation.status = ToolInvocationStatus.EXECUTED
                    invocation.result = record.result
                    invocation.completed_at = utc_now()
                    return invocation
                invocation.status = ToolInvocationStatus.FAILED
                invocation.sanitized_error = record.sanitized_error or "request already in progress"
                invocation.completed_at = utc_now()
                return invocation

        error_message: str | None = None
        for attempt in range(1, tool.max_attempts + 1):
            invocation.attempts = attempt
            try:
                invocation.result = tool.handler(arguments)
                invocation.status = ToolInvocationStatus.EXECUTED
                invocation.completed_at = utc_now()
                if idempotency_key is not None:
                    self.idempotency.complete(idempotency_key, invocation.result)
                return invocation
            except Exception as error:  # noqa: BLE001 - provider boundary is fail-closed
                error_message = self.redactor.redact(str(error))[:240]

        invocation.status = ToolInvocationStatus.FAILED
        invocation.sanitized_error = error_message or "tool failed"
        invocation.completed_at = utc_now()
        if idempotency_key is not None:
            self.idempotency.fail(idempotency_key, invocation.sanitized_error)
        return invocation
