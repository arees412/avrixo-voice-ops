"""Governed orchestration across policy, providers, tools, and session state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from time import perf_counter
from typing import Any
from uuid import uuid4

from .audit import AuditStore
from .escalation import HumanEscalationManager
from .metrics import MetricsCollector
from .models import (
    CallOutcome,
    ContactContext,
    ConversationTurn,
    OperationStatus,
    OutcomeClassification,
    PostCallSummary,
    SessionMetrics,
    SessionState,
    ToolInvocation,
    ToolInvocationStatus,
    VoiceOperation,
    VoiceSession,
    utc_now,
)
from .outcomes import GroundedSummaryBuilder, deterministic_outcome
from .policy import ContactPolicyEngine, ContactPolicyProfile
from .providers import ProviderBundle
from .redaction import TranscriptRedactor
from .state import SessionStateMachine
from .tools import GovernedToolRegistry


class ContactPolicyDenied(PermissionError):
    def __init__(self, reasons: tuple[str, ...]) -> None:
        super().__init__(f"contact policy denied operation: {', '.join(reasons)}")
        self.reasons = reasons


@dataclass(slots=True, frozen=True)
class CompletionReport:
    outcome: CallOutcome
    summary: PostCallSummary
    metrics: SessionMetrics


@dataclass(slots=True, frozen=True)
class _PendingToolCall:
    session_id: str
    tool_name: str
    arguments: dict[str, Any]
    idempotency_key: str | None


class VoiceOpsController:
    """Application service that keeps models from crossing governance boundaries."""

    def __init__(
        self,
        *,
        profile: ContactPolicyProfile,
        tools: GovernedToolRegistry | None = None,
        providers: ProviderBundle | None = None,
        redactor: TranscriptRedactor | None = None,
        audit: AuditStore | None = None,
        escalation: HumanEscalationManager | None = None,
    ) -> None:
        self.profile = profile
        self.redactor = redactor or TranscriptRedactor()
        self.tools = tools or GovernedToolRegistry(redactor=self.redactor)
        self.providers = providers
        self.audit = audit or AuditStore(self.redactor)
        self.escalation = escalation or HumanEscalationManager(
            lambda request: f"human-queue:{request.session_id}"
        )
        self.contact_policy = ContactPolicyEngine()
        self.operations: dict[str, VoiceOperation] = {}
        self.sessions: dict[str, VoiceSession] = {}
        self.turns: dict[str, list[ConversationTurn]] = {}
        self.invocations: dict[str, list[ToolInvocation]] = {}
        self.metrics: dict[str, MetricsCollector] = {}
        self._machines: dict[str, SessionStateMachine] = {}
        self._pending: dict[str, _PendingToolCall] = {}

    def create_operation(
        self,
        *,
        contact: ContactContext,
        purpose: str,
        at: datetime,
    ) -> VoiceOperation:
        result = self.contact_policy.evaluate(self.profile, contact, at=at)
        if not result.allowed:
            raise ContactPolicyDenied(result.reasons)
        operation = VoiceOperation(
            id=f"op_{uuid4().hex}",
            direction=contact.direction,
            purpose=purpose,
            policy_profile=self.profile.name,
            contact_reference=contact.reference,
        )
        self.operations[operation.id] = operation
        self.audit.append(operation.id, "operation.created", {"direction": operation.direction})
        return operation

    def start_session(self, operation_id: str) -> VoiceSession:
        operation = self.operations[operation_id]
        if operation.status is not OperationStatus.PENDING:
            raise ValueError("operation has already been started")
        session = VoiceSession(id=f"ses_{uuid4().hex}", operation_id=operation_id)
        machine = SessionStateMachine()
        machine.transition(SessionState.CONNECTING, "worker accepted operation")
        machine.transition(SessionState.ACTIVE, "realtime session connected")
        session.state = machine.state
        session.started_at = utc_now()
        operation.status = OperationStatus.RUNNING
        self.sessions[session.id] = session
        self.turns[session.id] = []
        self.invocations[session.id] = []
        provider_names: dict[str, str] = {}
        if self.providers is not None:
            provider_names = {
                "stt": self.providers.stt.name,
                "llm": self.providers.llm.name,
                "tts": self.providers.tts.name,
                "telephony": self.providers.telephony.name,
            }
            session.provider_configuration = provider_names
        self.metrics[session.id] = MetricsCollector(session.id, providers=provider_names)
        self._machines[session.id] = machine
        self.audit.append(session.id, "session.started", {"recording": False})
        return session

    def record_turn(
        self,
        session_id: str,
        *,
        speaker: str,
        transcript: str,
        confidence: float | None = None,
    ) -> ConversationTurn:
        self._require_state(session_id, {SessionState.ACTIVE, SessionState.AWAITING_APPROVAL})
        if confidence is not None and not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        sanitized = (
            self.redactor.redact(transcript)
            if self.profile.transcript_enabled
            else "[TRANSCRIPT_DISABLED]"
        )
        sequence = len(self.turns[session_id]) + 1
        turn = ConversationTurn(
            id=f"turn_{uuid4().hex}",
            session_id=session_id,
            sequence=sequence,
            speaker=speaker,
            transcript=sanitized,
            timestamp=utc_now(),
            confidence=confidence,
            redaction_state="redacted" if sanitized != transcript else "unchanged",
        )
        self.turns[session_id].append(turn)
        self.metrics[session_id].turns += 1
        self.audit.append(
            session_id,
            "conversation.turn",
            {"speaker": speaker, "sequence": sequence, "transcript": sanitized},
        )
        return turn

    def run_provider_exchange(self, session_id: str, audio: bytes) -> tuple[str, bytes]:
        """Run the injected STT/LLM/TTS chain and capture component latency."""

        self._require_state(session_id, {SessionState.ACTIVE})
        if self.providers is None:
            raise RuntimeError("no provider bundle configured")
        collector = self.metrics[session_id]
        started = perf_counter()
        transcript = self.providers.stt.transcribe(audio)
        collector.observe_latency("stt", (perf_counter() - started) * 1000)
        self.record_turn(session_id, speaker="contact", transcript=transcript)
        started = perf_counter()
        response = self.providers.llm.respond(transcript)
        collector.observe_latency("llm", (perf_counter() - started) * 1000)
        self.record_turn(session_id, speaker="agent", transcript=response)
        started = perf_counter()
        speech = self.providers.tts.synthesize(response)
        collector.observe_latency("tts", (perf_counter() - started) * 1000)
        if collector.time_to_first_response_ms is None:
            collector.time_to_first_response_ms = sum(
                series[0]
                for series in (
                    collector.stt_latency_ms,
                    collector.llm_latency_ms,
                    collector.tts_latency_ms,
                )
                if series
            )
        return response, speech

    def invoke_tool(
        self,
        session_id: str,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> ToolInvocation:
        self._require_state(session_id, {SessionState.ACTIVE})
        invocation_id = f"tool_{uuid4().hex}"
        started = perf_counter()
        invocation = self.tools.invoke(
            invocation_id=invocation_id,
            session_id=session_id,
            tool_name=tool_name,
            arguments=arguments,
            profile=self.profile,
            idempotency_key=idempotency_key,
        )
        self.metrics[session_id].observe_latency("tool", (perf_counter() - started) * 1000)
        self.metrics[session_id].tool_invocations += 1
        self.metrics[session_id].retries += max(0, invocation.attempts - 1)
        self.invocations[session_id].append(invocation)
        if invocation.status is ToolInvocationStatus.AWAITING_APPROVAL:
            self._pending[invocation.id] = _PendingToolCall(
                session_id=session_id,
                tool_name=tool_name,
                arguments=dict(arguments),
                idempotency_key=idempotency_key,
            )
            self._transition(session_id, SessionState.AWAITING_APPROVAL, "tool approval requested")
        self.audit.append(
            session_id,
            "tool.decision",
            {
                "tool": tool_name,
                "decision": invocation.policy_decision,
                "status": invocation.status,
                "approval_id": invocation.approval_id,
            },
        )
        return invocation

    def resolve_approval(
        self,
        invocation_id: str,
        *,
        approved: bool,
        decided_by: str,
        reason: str,
    ) -> ToolInvocation:
        pending = self._pending.pop(invocation_id)
        prior = self._find_invocation(pending.session_id, invocation_id)
        if prior.approval_id is None:
            raise RuntimeError("pending invocation has no approval")
        self.tools.approvals.resolve(
            prior.approval_id,
            approved=approved,
            decided_by=decided_by,
            reason=self.redactor.redact(reason),
        )
        updated = self.tools.invoke(
            invocation_id=invocation_id,
            session_id=pending.session_id,
            tool_name=pending.tool_name,
            arguments=pending.arguments,
            profile=self.profile,
            idempotency_key=pending.idempotency_key,
            approval_id=prior.approval_id,
        )
        self.invocations[pending.session_id][self.invocations[pending.session_id].index(prior)] = (
            updated
        )
        self.metrics[pending.session_id].retries += max(0, updated.attempts - 1)
        self._transition(pending.session_id, SessionState.ACTIVE, "tool approval resolved")
        self.audit.append(
            pending.session_id,
            "approval.resolved",
            {"approved": approved, "status": updated.status, "decided_by": decided_by},
        )
        return updated

    def escalate_to_human(
        self,
        session_id: str,
        *,
        reason: str,
        destination: str | None = None,
    ) -> str:
        self._require_state(session_id, {SessionState.ACTIVE, SessionState.AWAITING_APPROVAL})
        self._transition(session_id, SessionState.ESCALATING, "human escalation requested")
        sanitized_reason = self.redactor.redact(reason)
        request = self.escalation.request(
            session_id=session_id,
            reason=sanitized_reason,
            destination=destination,
        )
        self.sessions[session_id].escalation_status = request.status
        self.metrics[session_id].escalation_events += 1
        if request.status.value == "accepted":
            self._transition(session_id, SessionState.HANDOFF, "human accepted handoff")
        else:
            self._transition(session_id, SessionState.FAILED, "human handoff failed")
        self.audit.append(
            session_id,
            "escalation.completed",
            {"status": request.status, "reason": sanitized_reason},
        )
        return request.result or "handoff unavailable"

    def complete_session(
        self,
        session_id: str,
        *,
        classification: OutcomeClassification,
        disposition: str,
        follow_up_required: bool = False,
    ) -> CompletionReport:
        self._require_state(session_id, {SessionState.ACTIVE, SessionState.HANDOFF})
        session = self.sessions[session_id]
        operation = self.operations[session.operation_id]
        session.ended_at = utc_now()
        duration = (
            max(0.0, (session.ended_at - session.started_at).total_seconds())
            if session.started_at is not None
            else 0.0
        )
        outcome = deterministic_outcome(
            session_id=session_id,
            classification=classification,
            disposition=self.redactor.redact(disposition),
            follow_up_required=follow_up_required,
        )
        escalation_status = session.escalation_status
        summary = GroundedSummaryBuilder.build(
            outcome=outcome,
            turns=tuple(self.turns[session_id]),
            invocations=tuple(self.invocations[session_id]),
            duration_seconds=duration,
            escalation=escalation_status.value if escalation_status is not None else None,
        )
        self._transition(session_id, SessionState.COMPLETED, "structured outcome recorded")
        operation.status = OperationStatus.COMPLETED
        metrics = self.metrics[session_id].snapshot(duration)
        self.audit.append(
            session_id,
            "session.completed",
            {"outcome": outcome.classification, "duration_seconds": duration},
        )
        if not self.profile.transcript_retention_enabled:
            self.turns[session_id].clear()
        return CompletionReport(outcome=outcome, summary=summary, metrics=metrics)

    def _transition(self, session_id: str, target: SessionState, reason: str) -> None:
        machine = self._machines[session_id]
        machine.transition(target, reason)
        self.sessions[session_id].state = machine.state

    def _require_state(self, session_id: str, allowed: set[SessionState]) -> None:
        state = self.sessions[session_id].state
        if state not in allowed:
            raise ValueError(f"session state {state.value} does not allow this operation")

    def _find_invocation(self, session_id: str, invocation_id: str) -> ToolInvocation:
        return next(item for item in self.invocations[session_id] if item.id == invocation_id)
