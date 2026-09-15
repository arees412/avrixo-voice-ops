"""Typed VoiceOps domain records.

All timestamps are timezone-aware UTC values. The models deliberately contain no
provider SDK types, which keeps governance deterministic and independently testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


class Direction(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class OperationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SessionState(str, Enum):
    QUEUED = "queued"
    CONNECTING = "connecting"
    ACTIVE = "active"
    AWAITING_APPROVAL = "awaiting_approval"
    ESCALATING = "escalating"
    HANDOFF = "handoff"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRES_APPROVAL = "requires_approval"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class EscalationStatus(str, Enum):
    REQUESTED = "requested"
    ACCEPTED = "accepted"
    FAILED = "failed"


class OutcomeClassification(str, Enum):
    RESOLVED = "resolved"
    APPOINTMENT_BOOKED = "appointment_booked"
    QUALIFIED = "qualified"
    FOLLOW_UP_REQUIRED = "follow_up_required"
    HUMAN_HANDOFF = "human_handoff"
    NO_ANSWER = "no_answer"
    VOICEMAIL = "voicemail"
    WRONG_NUMBER = "wrong_number"
    DECLINED = "declined"
    FAILED = "failed"


class ToolInvocationStatus(str, Enum):
    PENDING = "pending"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTED = "executed"
    DENIED = "denied"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass(slots=True)
class ContactContext:
    reference: str
    direction: Direction
    consent_granted: bool = False
    do_not_contact: bool = False
    attempt: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class VoiceOperation:
    id: str
    direction: Direction
    purpose: str
    policy_profile: str
    contact_reference: str
    status: OperationStatus = OperationStatus.PENDING
    created_at: datetime = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class VoiceSession:
    id: str
    operation_id: str
    state: SessionState = SessionState.QUEUED
    livekit_session_id: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    disconnect_reason: str | None = None
    failure_reason: str | None = None
    escalation_status: EscalationStatus | None = None
    provider_configuration: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ConversationTurn:
    id: str
    session_id: str
    sequence: int
    speaker: str
    transcript: str
    timestamp: datetime
    confidence: float | None
    redaction_state: str


@dataclass(slots=True)
class ToolInvocation:
    id: str
    session_id: str
    tool_name: str
    arguments_summary: dict[str, Any]
    policy_decision: PolicyDecision
    status: ToolInvocationStatus
    started_at: datetime = field(default_factory=utc_now)
    completed_at: datetime | None = None
    attempts: int = 0
    sanitized_error: str | None = None
    approval_id: str | None = None
    idempotency_key: str | None = None
    result: Any = None


@dataclass(slots=True)
class ApprovalDecision:
    id: str
    session_id: str
    tool_invocation_id: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    requested_at: datetime = field(default_factory=utc_now)
    decided_at: datetime | None = None
    decided_by: str | None = None
    reason: str | None = None


@dataclass(slots=True)
class EscalationRequest:
    id: str
    session_id: str
    reason: str
    destination: str | None
    status: EscalationStatus = EscalationStatus.REQUESTED
    requested_at: datetime = field(default_factory=utc_now)
    accepted_at: datetime | None = None
    result: str | None = None


@dataclass(slots=True, frozen=True)
class CallOutcome:
    id: str
    session_id: str
    classification: OutcomeClassification
    confidence: float
    disposition: str
    follow_up_required: bool
    notes: str

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("outcome confidence must be between 0 and 1")


@dataclass(slots=True, frozen=True)
class PostCallSummary:
    summary: str
    outcome: OutcomeClassification
    key_facts: tuple[str, ...]
    actions_taken: tuple[str, ...]
    follow_up_actions: tuple[str, ...]
    escalation: str | None
    duration_seconds: float
    tool_usage: tuple[str, ...]
    transcript_reference: str | None


@dataclass(slots=True, frozen=True)
class SessionMetrics:
    session_id: str
    duration_seconds: float
    stt_latency_ms: tuple[float, ...]
    llm_latency_ms: tuple[float, ...]
    tts_latency_ms: tuple[float, ...]
    time_to_first_response_ms: float | None
    tool_latency_ms: tuple[float, ...]
    turns: int
    tool_invocations: int
    retries: int
    escalation_events: int
    providers: dict[str, str]
    token_usage: int | None = None


@dataclass(slots=True, frozen=True)
class WebhookDelivery:
    id: str
    event_type: str
    status_code: int | None
    attempts: int
    delivered: bool
    idempotency_key: str
    sanitized_error: str | None = None
