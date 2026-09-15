"""Human escalation and handoff boundary."""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from .models import EscalationRequest, EscalationStatus, utc_now

HandoffHandler = Callable[[EscalationRequest], str]


class HumanEscalationManager:
    """Route a redacted reason to an injected operator or telephony adapter."""

    def __init__(self, handler: HandoffHandler) -> None:
        self._handler = handler
        self._requests: dict[str, EscalationRequest] = {}

    def request(
        self,
        *,
        session_id: str,
        reason: str,
        destination: str | None,
    ) -> EscalationRequest:
        escalation = EscalationRequest(
            id=f"esc_{uuid4().hex}",
            session_id=session_id,
            reason=reason,
            destination=destination,
        )
        self._requests[escalation.id] = escalation
        try:
            escalation.result = self._handler(escalation)
            escalation.status = EscalationStatus.ACCEPTED
            escalation.accepted_at = utc_now()
        except Exception:  # noqa: BLE001 - external handoff boundary is fail-closed
            escalation.status = EscalationStatus.FAILED
            escalation.result = "handoff provider failed"
        return escalation

    def get(self, escalation_id: str) -> EscalationRequest:
        return self._requests[escalation_id]
