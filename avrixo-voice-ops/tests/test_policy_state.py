from datetime import datetime, time, timezone

import pytest

from avrixo_voice_ops.models import ContactContext, Direction, SessionState
from avrixo_voice_ops.policy import CallingWindow, ContactPolicyEngine, ContactPolicyProfile
from avrixo_voice_ops.state import InvalidSessionTransition, SessionStateMachine

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


def test_session_state_machine_accepts_expected_lifecycle() -> None:
    machine = SessionStateMachine()
    for state in (SessionState.CONNECTING, SessionState.ACTIVE, SessionState.COMPLETED):
        machine.transition(state, "test")
    assert machine.terminal
    assert [change.current for change in machine.history] == [
        SessionState.CONNECTING,
        SessionState.ACTIVE,
        SessionState.COMPLETED,
    ]


def test_session_state_machine_rejects_skipped_state() -> None:
    with pytest.raises(InvalidSessionTransition):
        SessionStateMachine().transition(SessionState.ACTIVE, "skip connect")


def test_contact_policy_denies_do_not_contact() -> None:
    profile = ContactPolicyProfile(name="inbound")
    contact = ContactContext("contact-1", Direction.INBOUND, True, do_not_contact=True)
    result = ContactPolicyEngine().evaluate(profile, contact, at=NOW)
    assert not result.allowed
    assert result.reasons == ("do_not_contact",)


def test_contact_policy_requires_consent() -> None:
    profile = ContactPolicyProfile(name="inbound")
    contact = ContactContext("contact-1", Direction.INBOUND)
    assert ContactPolicyEngine().evaluate(profile, contact, at=NOW).reasons == ("consent_required",)


def test_outbound_policy_enforces_window_and_retry_limit() -> None:
    profile = ContactPolicyProfile(
        name="outbound",
        inbound_only=False,
        outbound_enabled=True,
        timezone_name="UTC",
        calling_windows=(CallingWindow(time(9), time(17)),),
        max_retry_attempts=1,
    )
    contact = ContactContext("contact-1", Direction.OUTBOUND, True, attempt=3)
    result = ContactPolicyEngine().evaluate(profile, contact, at=NOW.replace(hour=20))
    assert result.reasons == ("retry_limit_exceeded", "outside_calling_window")


def test_overnight_calling_window_is_supported() -> None:
    window = CallingWindow(time(22), time(6))
    assert window.contains(NOW.replace(hour=23))
    assert not window.contains(NOW.replace(hour=12))


def test_recording_is_disabled_by_default_and_requires_consent() -> None:
    assert not ContactPolicyProfile(name="default").recording_enabled
    with pytest.raises(ValueError, match="consent"):
        ContactPolicyProfile(name="invalid", recording_enabled=True)
    enabled = ContactPolicyProfile(
        name="explicit",
        recording_enabled=True,
        recording_consent_confirmed=True,
    )
    assert enabled.recording_enabled


def test_policy_validates_duration_and_tool_overlap() -> None:
    profile = ContactPolicyProfile(name="short", maximum_session_duration_seconds=60)
    assert ContactPolicyEngine.duration_allowed(profile, 60)
    assert not ContactPolicyEngine.duration_allowed(profile, 61)
    with pytest.raises(ValueError, match="both allowed and restricted"):
        ContactPolicyProfile(
            name="invalid",
            allowed_tools=frozenset({"crm"}),
            restricted_tools=frozenset({"crm"}),
        )
