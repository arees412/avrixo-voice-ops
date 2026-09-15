"""Non-secret deployment readiness checks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class ReadinessReport:
    ready: bool
    checks: dict[str, bool]
    reasons: tuple[str, ...]


def readiness_check(
    *,
    configured_providers: dict[str, str],
    webhook_secret_present: bool,
    recording_enabled: bool = False,
    recording_consent_confirmed: bool = False,
) -> ReadinessReport:
    required = ("stt", "llm", "tts", "telephony")
    checks = {f"provider_{name}": bool(configured_providers.get(name)) for name in required}
    checks["webhook_secret"] = webhook_secret_present
    checks["recording_consent"] = not recording_enabled or recording_consent_confirmed
    reasons = tuple(name for name, passed in checks.items() if not passed)
    return ReadinessReport(ready=not reasons, checks=checks, reasons=reasons)
