from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def _safe_mean(values: Iterable[float]) -> float:
    items = list(values)
    if not items:
        return 0.0
    return sum(items) / len(items)

#EVALUATION METRICS FOR TRIAGE DECISIONS, INCLUDING ACCURACY AND COMPARISON TO GOLD STANDARD
def accuracy_score(actual: list[Any], predicted: list[Any]) -> float:
    if len(actual) != len(predicted):
        raise ValueError("actual and predicted lengths must match.")
    if not actual:
        return 0.0
    matches = sum(1 for a, p in zip(actual, predicted) if a == p)
    return matches / len(actual)


def evaluate_triage(predictions: list[dict[str, Any]], gold: list[dict[str, Any]]) -> dict[str, float]:
    actual_urgency = [item["urgency"] for item in gold]
    predicted_urgency = [item["urgency"] for item in predictions]
    actual_actions = [item["action"] for item in gold]
    predicted_actions = [item["action"] for item in predictions]
    return {
        "urgency_accuracy": accuracy_score(actual_urgency, predicted_urgency),
        "action_accuracy": accuracy_score(actual_actions, predicted_actions),
        "overall_accuracy": _safe_mean([
            accuracy_score(actual_urgency, predicted_urgency),
            accuracy_score(actual_actions, predicted_actions),
        ]),
    }


__all__ = ["accuracy_score", "evaluate_triage"]
