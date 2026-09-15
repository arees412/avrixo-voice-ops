from datetime import datetime, timezone

from avrixo_voice_ops.controller import VoiceOpsController
from avrixo_voice_ops.escalation import HumanEscalationManager
from avrixo_voice_ops.models import (
    ContactContext,
    Direction,
    OutcomeClassification,
    SessionState,
    ToolInvocationStatus,
)
from avrixo_voice_ops.policy import ContactPolicyProfile
from avrixo_voice_ops.providers import (
    DeterministicLLM,
    DeterministicSTT,
    DeterministicTelephony,
    DeterministicTTS,
    ProviderBundle,
)
from avrixo_voice_ops.redaction import RedactionPolicy, TranscriptRedactor
from avrixo_voice_ops.tools import GovernedToolRegistry, ToolDefinition

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


def controller_for(*allowed_tools: str) -> VoiceOpsController:
    redactor = TranscriptRedactor(RedactionPolicy(redact_email=True, redact_phone=True))
    tools = GovernedToolRegistry(redactor=redactor)
    providers = ProviderBundle(
        stt=DeterministicSTT("I need the status for person@example.com"),
        llm=DeterministicLLM("I found the account status."),
        tts=DeterministicTTS(),
        telephony=DeterministicTelephony(),
    )
    return VoiceOpsController(
        profile=ContactPolicyProfile(
            name="e2e",
            allowed_tools=frozenset(allowed_tools),
            transcript_retention_enabled=False,
        ),
        tools=tools,
        providers=providers,
        redactor=redactor,
    )


def start(controller: VoiceOpsController) -> str:
    operation = controller.create_operation(
        contact=ContactContext("contact-1", Direction.INBOUND, consent_granted=True),
        purpose="customer support",
        at=NOW,
    )
    return controller.start_session(operation.id).id


def test_e2e_allowed_crm_lookup_and_grounded_summary() -> None:
    controller = controller_for("crm_lookup")
    controller.tools.register(
        ToolDefinition("crm_lookup", "read account status", lambda _args: {"status": "active"})
    )
    session_id = start(controller)
    response, audio = controller.run_provider_exchange(session_id, b"deterministic audio")
    invocation = controller.invoke_tool(
        session_id,
        tool_name="crm_lookup",
        arguments={"contact": "person@example.com"},
        idempotency_key="lookup-1",
    )
    report = controller.complete_session(
        session_id,
        classification=OutcomeClassification.RESOLVED,
        disposition="Account status returned",
    )
    assert response == "I found the account status."
    assert audio == b"VOICE:I found the account status."
    assert invocation.status is ToolInvocationStatus.EXECUTED
    assert report.outcome.classification is OutcomeClassification.RESOLVED
    assert report.summary.actions_taken == ("crm_lookup",)
    assert "person@example.com" not in " ".join(report.summary.key_facts)
    assert controller.turns[session_id] == []
    assert controller.audit.verify_chain()


def test_e2e_approval_rejection_prevents_side_effect() -> None:
    calls = 0

    def update(_args: object) -> dict[str, bool]:
        nonlocal calls
        calls += 1
        return {"updated": True}

    controller = controller_for("crm_update")
    controller.tools.register(ToolDefinition("crm_update", "update CRM", update, side_effect=True))
    session_id = start(controller)
    pending = controller.invoke_tool(
        session_id,
        tool_name="crm_update",
        arguments={"status": "closed"},
        idempotency_key="update-1",
    )
    assert controller.sessions[session_id].state is SessionState.AWAITING_APPROVAL
    rejected = controller.resolve_approval(
        pending.id,
        approved=False,
        decided_by="operator-1",
        reason="contact did not authorize the update",
    )
    assert rejected.status is ToolInvocationStatus.REJECTED
    assert calls == 0
    assert controller.sessions[session_id].state is SessionState.ACTIVE


def test_e2e_human_handoff_reaches_explicit_handoff_state() -> None:
    controller = controller_for()
    controller.escalation = HumanEscalationManager(lambda request: f"accepted:{request.session_id}")
    session_id = start(controller)
    result = controller.escalate_to_human(
        session_id,
        reason="Contact requested a supervisor",
        destination="support-queue",
    )
    assert result == f"accepted:{session_id}"
    assert controller.sessions[session_id].state is SessionState.HANDOFF
    report = controller.complete_session(
        session_id,
        classification=OutcomeClassification.HUMAN_HANDOFF,
        disposition="Transferred to the support queue",
    )
    assert report.summary.escalation == "accepted"
    assert report.metrics.escalation_events == 1
