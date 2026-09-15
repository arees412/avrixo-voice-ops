"""Deterministic governance evaluation harness."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .models import OutcomeClassification, PolicyDecision


@dataclass(slots=True, frozen=True)
class EvaluationObservation:
    outcome: OutcomeClassification
    tool_decisions: tuple[PolicyDecision, ...]
    summary: str


@dataclass(slots=True, frozen=True)
class EvaluationCase:
    id: str
    description: str
    expected_outcome: OutcomeClassification
    expected_tool_decisions: tuple[PolicyDecision, ...]
    prohibited_summary_terms: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class EvaluationResult:
    case_id: str
    passed: bool
    failures: tuple[str, ...]


EvaluationRunner = Callable[[EvaluationCase], EvaluationObservation]


class EvaluationHarness:
    def __init__(self, runner: EvaluationRunner) -> None:
        self.runner = runner

    def run(self, cases: tuple[EvaluationCase, ...]) -> tuple[EvaluationResult, ...]:
        results: list[EvaluationResult] = []
        for case in cases:
            observation = self.runner(case)
            failures: list[str] = []
            if observation.outcome is not case.expected_outcome:
                failures.append("outcome_mismatch")
            if observation.tool_decisions != case.expected_tool_decisions:
                failures.append("tool_decision_mismatch")
            normalized_summary = observation.summary.casefold()
            if any(term.casefold() in normalized_summary for term in case.prohibited_summary_terms):
                failures.append("prohibited_summary_content")
            results.append(EvaluationResult(case.id, not failures, tuple(failures)))
        return tuple(results)

    def assert_all_pass(self, cases: tuple[EvaluationCase, ...]) -> None:
        failures = [result for result in self.run(cases) if not result.passed]
        if failures:
            details = ", ".join(f"{item.case_id}:{'/'.join(item.failures)}" for item in failures)
            raise AssertionError(f"evaluation failures: {details}")
