"""One-time approval gate for sensitive model-requested side effects."""

from __future__ import annotations

from uuid import uuid4

from .models import ApprovalDecision, ApprovalStatus, utc_now


class ApprovalNotFound(KeyError):
    pass


class ApprovalAlreadyDecided(ValueError):
    pass


class ApprovalGate:
    """Create and resolve explicit approvals without model self-authorization."""

    def __init__(self) -> None:
        self._decisions: dict[str, ApprovalDecision] = {}

    def request(self, session_id: str, tool_invocation_id: str) -> ApprovalDecision:
        decision = ApprovalDecision(
            id=f"apr_{uuid4().hex}",
            session_id=session_id,
            tool_invocation_id=tool_invocation_id,
        )
        self._decisions[decision.id] = decision
        return decision

    def get(self, approval_id: str) -> ApprovalDecision:
        try:
            return self._decisions[approval_id]
        except KeyError as error:
            raise ApprovalNotFound(approval_id) from error

    def resolve(
        self,
        approval_id: str,
        *,
        approved: bool,
        decided_by: str,
        reason: str,
    ) -> ApprovalDecision:
        decision = self.get(approval_id)
        if decision.status is not ApprovalStatus.PENDING:
            raise ApprovalAlreadyDecided(approval_id)
        decision.status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        decision.decided_at = utc_now()
        decision.decided_by = decided_by
        decision.reason = reason
        return decision

    def is_approved(self, approval_id: str, invocation_id: str) -> bool:
        decision = self.get(approval_id)
        return (
            decision.tool_invocation_id == invocation_id
            and decision.status is ApprovalStatus.APPROVED
        )

    def pending(self, session_id: str) -> tuple[ApprovalDecision, ...]:
        return tuple(
            item
            for item in self._decisions.values()
            if item.session_id == session_id and item.status is ApprovalStatus.PENDING
        )
