"""Low-cardinality operational metrics without transcript or contact content."""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import SessionMetrics


@dataclass(slots=True)
class MetricsCollector:
    session_id: str
    providers: dict[str, str] = field(default_factory=dict)
    stt_latency_ms: list[float] = field(default_factory=list)
    llm_latency_ms: list[float] = field(default_factory=list)
    tts_latency_ms: list[float] = field(default_factory=list)
    tool_latency_ms: list[float] = field(default_factory=list)
    time_to_first_response_ms: float | None = None
    turns: int = 0
    tool_invocations: int = 0
    retries: int = 0
    escalation_events: int = 0
    token_usage: int | None = None

    def observe_latency(self, stage: str, milliseconds: float) -> None:
        if milliseconds < 0:
            raise ValueError("latency cannot be negative")
        latency_series = {
            "stt": self.stt_latency_ms,
            "llm": self.llm_latency_ms,
            "tts": self.tts_latency_ms,
            "tool": self.tool_latency_ms,
        }
        try:
            latency_series[stage].append(milliseconds)
        except KeyError as error:
            raise ValueError(f"unknown latency stage: {stage}") from error

    def snapshot(self, duration_seconds: float) -> SessionMetrics:
        return SessionMetrics(
            session_id=self.session_id,
            duration_seconds=max(0.0, duration_seconds),
            stt_latency_ms=tuple(self.stt_latency_ms),
            llm_latency_ms=tuple(self.llm_latency_ms),
            tts_latency_ms=tuple(self.tts_latency_ms),
            time_to_first_response_ms=self.time_to_first_response_ms,
            tool_latency_ms=tuple(self.tool_latency_ms),
            turns=self.turns,
            tool_invocations=self.tool_invocations,
            retries=self.retries,
            escalation_events=self.escalation_events,
            providers=dict(self.providers),
            token_usage=self.token_usage,
        )
