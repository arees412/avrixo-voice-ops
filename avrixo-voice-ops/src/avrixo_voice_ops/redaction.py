"""Deterministic transcript and audit redaction."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class RedactionPolicy:
    redact_email: bool = False
    redact_phone: bool = False


class TranscriptRedactor:
    """Mask credential-like and policy-selected personal data."""

    _bearer = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]{8,}")
    _api_key = re.compile(r"\b(?:sk|pk|api)[-_][A-Za-z0-9_-]{12,}\b")
    _password = re.compile(r"(?i)\b(password|passwd|pwd)\s*[:=]\s*\S+")
    _auth_code = re.compile(
        r"(?i)\b(otp|auth(?:entication)?\s+code|verification\s+code)\s*[:=]?\s*\d{4,8}\b"
    )
    _email = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
    _phone = re.compile(r"(?<!\w)(?:\+?\d[\s().-]*){7,15}(?!\w)")
    _card = re.compile(r"(?<!\d)(?:\d[ -]*?){13,19}(?!\d)")

    def __init__(self, policy: RedactionPolicy | None = None) -> None:
        self.policy = policy or RedactionPolicy()

    def redact(self, text: str) -> str:
        value = self._bearer.sub("[REDACTED_BEARER]", text)
        value = self._api_key.sub("[REDACTED_API_KEY]", value)
        value = self._password.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)
        value = self._auth_code.sub(lambda match: f"{match.group(1)} [REDACTED]", value)
        value = self._card.sub(self._mask_card_like, value)
        if self.policy.redact_email:
            value = self._email.sub("[REDACTED_EMAIL]", value)
        if self.policy.redact_phone:
            value = self._phone.sub("[REDACTED_PHONE]", value)
        return value

    def redact_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.redact(value)
        if isinstance(value, dict):
            return {str(key): self.redact_value(item) for key, item in value.items()}
        if isinstance(value, list | tuple):
            return [self.redact_value(item) for item in value]
        return value

    @staticmethod
    def _mask_card_like(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group(0))
        if len(digits) < 13:
            return match.group(0)
        return f"[REDACTED_CARD_ENDING_{digits[-4:]}]"
