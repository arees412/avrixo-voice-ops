"""Structured outcomes and transcript-grounded post-call summaries."""

from __future__ import annotations

import hashlib

from .models import (
    CallOutcome,
    ConversationTurn,
    OutcomeClassification,
    PostCallSummary,
    ToolInvocation,
    ToolInvocationStatus,
)


class GroundedSummaryBuilder:
    """Build a summary only from already-redacted stored session evidence."""

    @staticmethod
    def build(
        *,
        outcome: CallOutcome,
        turns: tuple[ConversationTurn, ...],
        invocations: tuple[ToolInvocation, ...],
        duration_seconds: float,
        escalation: str | None = None,
    ) -> PostCallSummary:
        evidence = tuple(turn.transcript.strip()[:180] for turn in turns if turn.transcript.strip())
        key_facts = tuple(dict.fromkeys(evidence))[:3]
        executed_tools = tuple(
            invocation.tool_name
            for invocation in invocations
            if invocation.status is ToolInvocationStatus.EXECUTED
        )
        follow_up = (
            ("Follow-up required by the structured outcome.",) if outcome.follow_up_required else ()
        )
        transcript_reference = None
        if evidence:
            digest = hashlib.sha256("\n".join(evidence).encode()).hexdigest()[:16]
            transcript_reference = f"sha256:{digest}"
        return PostCallSummary(
            summary=f"{outcome.classification.value}: {outcome.disposition}",
            outcome=outcome.classification,
            key_facts=key_facts,
            actions_taken=tuple(dict.fromkeys(executed_tools)),
            follow_up_actions=follow_up,
            escalation=escalation,
            duration_seconds=max(0.0, duration_seconds),
            tool_usage=tuple(invocation.tool_name for invocation in invocations),
            transcript_reference=transcript_reference,
        )


def deterministic_outcome(
    *,
    session_id: str,
    classification: OutcomeClassification,
    disposition: str,
    follow_up_required: bool = False,
) -> CallOutcome:
    """Create an explicit outcome without asking an LLM to invent a disposition."""

    digest = hashlib.sha256(
        f"{session_id}:{classification.value}:{disposition}".encode()
    ).hexdigest()[:20]
    return CallOutcome(
        id=f"out_{digest}",
        session_id=session_id,
        classification=classification,
        confidence=1.0,
        disposition=disposition,
        follow_up_required=follow_up_required,
        notes="Deterministic outcome selected by the workflow.",
    )
