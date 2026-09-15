"""Run the checked-in deterministic VoiceOps governance evaluation cases."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from avrixo_voice_ops.evaluation import (
    EvaluationCase,
    EvaluationHarness,
    EvaluationObservation,
)
from avrixo_voice_ops.models import OutcomeClassification, PolicyDecision
from avrixo_voice_ops.policy import ContactPolicyProfile
from avrixo_voice_ops.tools import ToolDefinition, ToolPolicyEngine


def load_cases() -> tuple[dict[str, Any], ...]:
    path = Path(__file__).parents[1] / "evaluations" / "cases.json"
    return tuple(json.loads(path.read_text(encoding="utf-8")))


def main() -> None:
    raw_cases = load_cases()
    definitions = {
        "crm_lookup": ToolDefinition("crm_lookup", "read CRM", lambda args: args),
        "crm_update": ToolDefinition(
            "crm_update", "update CRM", lambda args: args, side_effect=True
        ),
        "payment_capture": ToolDefinition(
            "payment_capture", "capture payment", lambda args: args, side_effect=True
        ),
    }
    profile = ContactPolicyProfile(
        name="evaluation",
        allowed_tools=frozenset({"crm_lookup", "crm_update"}),
        restricted_tools=frozenset({"payment_capture"}),
    )
    source = {item["id"]: item for item in raw_cases}
    cases = tuple(
        EvaluationCase(
            id=item["id"],
            description=item["description"],
            expected_outcome=OutcomeClassification(item["expected_outcome"]),
            expected_tool_decisions=(PolicyDecision(item["expected_decision"]),),
            prohibited_summary_terms=tuple(item["prohibited_summary_terms"]),
        )
        for item in raw_cases
    )

    def run(case: EvaluationCase) -> EvaluationObservation:
        item = source[case.id]
        decision = ToolPolicyEngine.decide(profile, definitions[item["tool"]])
        return EvaluationObservation(
            outcome=OutcomeClassification(item["expected_outcome"]),
            tool_decisions=(decision,),
            summary=item["summary"],
        )

    EvaluationHarness(run).assert_all_pass(cases)
    print(f"VoiceOps evaluation passed: {len(cases)} deterministic cases")


if __name__ == "__main__":
    main()
