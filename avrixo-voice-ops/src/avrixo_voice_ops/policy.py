"""Pre-session contact and consent policy controls."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import ContactContext, Direction


@dataclass(slots=True, frozen=True)
class CallingWindow:
    start: time
    end: time
    weekdays: frozenset[int] = frozenset(range(7))

    def contains(self, local_time: datetime) -> bool:
        if local_time.weekday() not in self.weekdays:
            return False
        current = local_time.timetz().replace(tzinfo=None)
        if self.start <= self.end:
            return self.start <= current < self.end
        return current >= self.start or current < self.end


@dataclass(slots=True, frozen=True)
class ContactPolicyProfile:
    name: str
    inbound_only: bool = True
    outbound_enabled: bool = False
    consent_required: bool = True
    timezone_name: str = "UTC"
    calling_windows: tuple[CallingWindow, ...] = ()
    max_retry_attempts: int = 2
    maximum_session_duration_seconds: int = 900
    allowed_tools: frozenset[str] = frozenset()
    restricted_tools: frozenset[str] = frozenset()
    approval_required_tools: frozenset[str] = frozenset()
    recording_enabled: bool = False
    recording_consent_confirmed: bool = False
    transcript_enabled: bool = True
    transcript_retention_enabled: bool = False

    def __post_init__(self) -> None:
        if self.max_retry_attempts < 0:
            raise ValueError("max_retry_attempts cannot be negative")
        if self.maximum_session_duration_seconds <= 0:
            raise ValueError("maximum_session_duration_seconds must be positive")
        if self.recording_enabled and not self.recording_consent_confirmed:
            raise ValueError("recording requires an explicit consent confirmation")
        if self.allowed_tools & self.restricted_tools:
            raise ValueError("a tool cannot be both allowed and restricted")


@dataclass(slots=True, frozen=True)
class ContactPolicyResult:
    allowed: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)


class ContactPolicyEngine:
    def evaluate(
        self,
        profile: ContactPolicyProfile,
        contact: ContactContext,
        *,
        at: datetime,
    ) -> ContactPolicyResult:
        reasons: list[str] = []
        if contact.do_not_contact:
            reasons.append("do_not_contact")
        if contact.direction is Direction.OUTBOUND:
            if profile.inbound_only or not profile.outbound_enabled:
                reasons.append("outbound_disabled")
            if contact.attempt > profile.max_retry_attempts + 1:
                reasons.append("retry_limit_exceeded")
            if profile.calling_windows:
                try:
                    target_zone = (
                        timezone.utc
                        if profile.timezone_name in {"UTC", "Etc/UTC"}
                        else ZoneInfo(profile.timezone_name)
                    )
                except ZoneInfoNotFoundError as error:
                    raise ValueError(
                        f"timezone data unavailable for {profile.timezone_name!r}"
                    ) from error
                local = at.astimezone(target_zone)
                if not any(window.contains(local) for window in profile.calling_windows):
                    reasons.append("outside_calling_window")
        if profile.consent_required and not contact.consent_granted:
            reasons.append("consent_required")
        return ContactPolicyResult(not reasons, tuple(reasons))

    @staticmethod
    def duration_allowed(profile: ContactPolicyProfile, duration_seconds: float) -> bool:
        return duration_seconds <= profile.maximum_session_duration_seconds
