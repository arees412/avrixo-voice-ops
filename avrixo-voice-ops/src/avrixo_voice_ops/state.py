"""Explicit, validated realtime session state machine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .models import SessionState, utc_now


class InvalidSessionTransition(ValueError):
    """Raised when a transition would create an impossible session state."""


_TRANSITIONS: dict[SessionState, frozenset[SessionState]] = {
    SessionState.QUEUED: frozenset(
        {SessionState.CONNECTING, SessionState.CANCELLED, SessionState.FAILED}
    ),
    SessionState.CONNECTING: frozenset(
        {SessionState.ACTIVE, SessionState.CANCELLED, SessionState.FAILED}
    ),
    SessionState.ACTIVE: frozenset(
        {
            SessionState.AWAITING_APPROVAL,
            SessionState.ESCALATING,
            SessionState.COMPLETED,
            SessionState.CANCELLED,
            SessionState.FAILED,
        }
    ),
    SessionState.AWAITING_APPROVAL: frozenset(
        {
            SessionState.ACTIVE,
            SessionState.ESCALATING,
            SessionState.CANCELLED,
            SessionState.FAILED,
        }
    ),
    SessionState.ESCALATING: frozenset(
        {SessionState.HANDOFF, SessionState.CANCELLED, SessionState.FAILED}
    ),
    SessionState.HANDOFF: frozenset(
        {SessionState.COMPLETED, SessionState.CANCELLED, SessionState.FAILED}
    ),
    SessionState.COMPLETED: frozenset(),
    SessionState.CANCELLED: frozenset(),
    SessionState.FAILED: frozenset(),
}


@dataclass(slots=True, frozen=True)
class StateTransition:
    previous: SessionState
    current: SessionState
    reason: str
    timestamp: datetime


class SessionStateMachine:
    """Maintain the current state and an immutable transition history."""

    def __init__(self, initial: SessionState = SessionState.QUEUED) -> None:
        self._state = initial
        self._history: list[StateTransition] = []

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def history(self) -> tuple[StateTransition, ...]:
        return tuple(self._history)

    def can_transition(self, target: SessionState) -> bool:
        return target in _TRANSITIONS[self._state]

    def transition(self, target: SessionState, reason: str) -> StateTransition:
        if not self.can_transition(target):
            raise InvalidSessionTransition(
                f"cannot transition {self._state.value} -> {target.value}"
            )
        change = StateTransition(self._state, target, reason, utc_now())
        self._state = target
        self._history.append(change)
        return change

    @property
    def terminal(self) -> bool:
        return not _TRANSITIONS[self._state]
