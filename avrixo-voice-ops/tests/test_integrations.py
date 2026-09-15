import asyncio
import json
from collections.abc import Mapping

import pytest

from avrixo_voice_ops.evaluation import (
    EvaluationCase,
    EvaluationHarness,
    EvaluationObservation,
)
from avrixo_voice_ops.health import readiness_check
from avrixo_voice_ops.livekit_adapter import LiveKitSessionAdapter
from avrixo_voice_ops.models import OutcomeClassification, PolicyDecision
from avrixo_voice_ops.providers import (
    DeterministicLLM,
    DeterministicSTT,
    DeterministicTelephony,
    DeterministicTTS,
)
from avrixo_voice_ops.webhooks import WebhookDispatcher, WebhookSigner


def test_webhook_signature_round_trip() -> None:
    signer = WebhookSigner("test-secret-with-enough-entropy")
    body = b'{"event":"completed"}'
    signature = signer.sign(body, 1_700_000_000)
    assert signer.verify(body, signature, timestamp=1_700_000_000)
    assert not signer.verify(body + b"x", signature, timestamp=1_700_000_000)


def test_webhook_is_redacted_signed_and_idempotent() -> None:
    requests: list[tuple[Mapping[str, str], bytes]] = []

    def transport(_url: str, headers: Mapping[str, str], body: bytes) -> int:
        requests.append((headers, body))
        return 204

    dispatcher = WebhookDispatcher(
        signer=WebhookSigner("test-secret-with-enough-entropy"),
        transport=transport,
    )
    first = dispatcher.deliver(
        url="https://example.invalid/hooks",
        event_type="session.completed",
        payload={"note": "password=secret"},
        idempotency_key="event-1",
        timestamp=1_700_000_000,
    )
    second = dispatcher.deliver(
        url="https://example.invalid/hooks",
        event_type="session.completed",
        payload={"note": "password=secret"},
        idempotency_key="event-1",
        timestamp=1_700_000_000,
    )
    assert first is second
    assert len(requests) == 1
    assert "secret" not in json.loads(requests[0][1])["note"]
    assert "x-avrixo-signature" in requests[0][0]


def test_webhook_retries_are_bounded() -> None:
    attempts = 0

    def transport(_url: str, _headers: Mapping[str, str], _body: bytes) -> int:
        nonlocal attempts
        attempts += 1
        return 503

    delivery = WebhookDispatcher(
        signer=WebhookSigner("test-secret-with-enough-entropy"),
        transport=transport,
        max_attempts=3,
    ).deliver(
        url="https://example.invalid/hooks",
        event_type="test",
        payload={},
        idempotency_key="event-1",
        timestamp=1_700_000_000,
    )
    assert attempts == delivery.attempts == 3
    assert not delivery.delivered


def test_webhook_rejects_insecure_destination() -> None:
    dispatcher = WebhookDispatcher(
        signer=WebhookSigner("test-secret-with-enough-entropy"),
        transport=lambda _url, _headers, _body: 200,
    )
    with pytest.raises(ValueError, match="HTTPS"):
        dispatcher.deliver(
            url="http://example.invalid/hooks",
            event_type="test",
            payload={},
            idempotency_key="event-1",
            timestamp=1_700_000_000,
        )


def test_evaluation_harness_reports_governance_failures() -> None:
    case = EvaluationCase(
        id="case-1",
        description="deny unsafe action",
        expected_outcome=OutcomeClassification.DECLINED,
        expected_tool_decisions=(PolicyDecision.DENY,),
        prohibited_summary_terms=("account number",),
    )
    harness = EvaluationHarness(
        lambda _case: EvaluationObservation(
            OutcomeClassification.RESOLVED,
            (PolicyDecision.ALLOW,),
            "Contains account number",
        )
    )
    result = harness.run((case,))[0]
    assert result.failures == (
        "outcome_mismatch",
        "tool_decision_mismatch",
        "prohibited_summary_content",
    )


def test_readiness_requires_all_providers_and_recording_consent() -> None:
    report = readiness_check(
        configured_providers={"stt": "fake", "llm": "fake"},
        webhook_secret_present=False,
        recording_enabled=True,
    )
    assert not report.ready
    assert "provider_tts" in report.reasons
    assert "recording_consent" in report.reasons


def test_deterministic_providers_have_no_external_dependencies() -> None:
    stt = DeterministicSTT("hello")
    llm = DeterministicLLM("hi")
    tts = DeterministicTTS()
    telephony = DeterministicTelephony()
    assert stt.transcribe(b"audio") == "hello"
    assert llm.respond("hello") == "hi"
    assert tts.synthesize("hi") == b"VOICE:hi"
    assert telephony.connect("session", "+15555550100") == "call-session"
    assert telephony.transfer("session", "operator") == "handoff-session"
    telephony.end("session")
    assert [event[0] for event in telephony.events] == ["connect", "transfer", "end"]


def test_livekit_start_adapter_forces_recording_off() -> None:
    class FakeSession:
        async def start(self, **options: object) -> dict[str, object]:
            return options

    result = asyncio.run(LiveKitSessionAdapter.start_session(FakeSession(), agent="agent"))
    assert result == {"agent": "agent", "record": False}
    with pytest.raises(ValueError, match="consent-gated"):
        asyncio.run(LiveKitSessionAdapter.start_session(FakeSession(), agent="agent", record=True))
