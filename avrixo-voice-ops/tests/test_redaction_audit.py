from avrixo_voice_ops.audit import AuditStore
from avrixo_voice_ops.redaction import RedactionPolicy, TranscriptRedactor


def test_redactor_masks_credentials_codes_and_cards() -> None:
    source = (
        "Bearer abcdefghijklmnop password=hunter2 OTP 123456 "
        "card 4111 1111 1111 1111 api-abcdefghijklmnop"
    )
    redacted = TranscriptRedactor().redact(source)
    assert "abcdefghijklmnop" not in redacted
    assert "hunter2" not in redacted
    assert "123456" not in redacted
    assert "4111 1111 1111 1111" not in redacted
    assert "ENDING_1111" in redacted


def test_redactor_optionally_masks_email_and_phone() -> None:
    redactor = TranscriptRedactor(RedactionPolicy(redact_email=True, redact_phone=True))
    result = redactor.redact("person@example.com at +1 (415) 555-0199")
    assert "person@example.com" not in result
    assert "415" not in result


def test_redactor_handles_nested_values() -> None:
    result = TranscriptRedactor().redact_value({"items": ["password=secret", "safe"]})
    assert result == {"items": ["password=[REDACTED]", "safe"]}


def test_audit_store_redacts_and_verifies_hash_chain() -> None:
    audit = AuditStore()
    audit.append("session", "test", {"message": "password=secret"})
    audit.append("session", "test2", {"safe": True})
    assert "secret" not in audit.export_jsonl()
    assert audit.verify_chain()
    assert len(audit.for_session("session")) == 2


def test_audit_store_detects_tampering() -> None:
    audit = AuditStore()
    record = audit.append("session", "test", {"safe": True})
    object.__setattr__(record, "record_hash", "tampered")
    assert not audit.verify_chain()
