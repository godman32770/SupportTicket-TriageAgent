from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

from app.guardrails.policy import PolicyGuardrail


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


def _optional_accuracy(
    predictions: list[dict[str, Any]],
    gold: list[dict[str, Any]],
    field: str,
) -> float | None:
    labeled = [
        (expected[field], prediction[field])
        for prediction, expected in zip(predictions, gold)
        if field in prediction and field in expected
    ]
    if not labeled:
        return None

    if field == "intents":
        return accuracy_score(
            [frozenset(actual) for actual, _ in labeled],
            [frozenset(predicted) for _, predicted in labeled],
        )
    return accuracy_score(
        [actual for actual, _ in labeled],
        [predicted for _, predicted in labeled],
    )


def _has_kb_evidence(summary: Any) -> bool:
    text = str(summary or "").strip().lower()
    return bool(text) and not any(
        phrase in text
        for phrase in ("no matching kb", "no matching entries", "general support workflow")
    )


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def _precision_recall(actual: list[str], predicted: list[str], label: str) -> tuple[float, float]:
    tp = sum(a == label and p == label for a, p in zip(actual, predicted))
    fp = sum(a != label and p == label for a, p in zip(actual, predicted))
    fn = sum(a == label and p != label for a, p in zip(actual, predicted))
    return (tp / (tp + fp) if tp + fp else 0.0, tp / (tp + fn) if tp + fn else 0.0)


def evaluate_triage(predictions: list[dict[str, Any]], gold: list[dict[str, Any]]) -> dict[str, Any]:
    if len(predictions) != len(gold):
        raise ValueError("predictions and gold lengths must match.")

    predicted_urgency = [str(item.get("urgency", "")) for item in predictions]
    expected_urgency = [
        item.get("urgency", "")
        if isinstance(item.get("urgency", ""), list)
        else [item.get("urgency", "")]
        for item in gold
    ]
    primary_urgency = [
        str(labels[0]) if labels else ""
        for labels in expected_urgency
    ]
    actual_actions = [str(item.get("action", "")) for item in gold]
    predicted_actions = [str(item.get("action", "")) for item in predictions]
    urgency_matches = [
        prediction in labels
        for prediction, labels in zip(predicted_urgency, expected_urgency, strict=False)
    ]
    action_matches = [
        prediction == expected
        for prediction, expected in zip(predicted_actions, actual_actions, strict=False)
    ]
    pair_matches = [
        urgency_ok and action_ok
        for urgency_ok, action_ok in zip(urgency_matches, action_matches, strict=False)
    ]
    fallback_predictions = [
        prediction
        for prediction in predictions
        if "error" in prediction
        or "fallback guardrail applied" in str(prediction.get("safety_checks", []))
        or "Fallback triggered" in str(prediction.get("reasoning", ""))
    ]
    auto_respond_predictions = [
        item for item in predictions if str(item.get("action", "")).lower() == "auto_respond"
    ]
    result: dict[str, Any] = {
        "urgency_accuracy": _safe_mean(urgency_matches),
        "action_accuracy": _safe_mean(action_matches),
        "overall_accuracy": _safe_mean(pair_matches),
        "fallback_rate": _safe_mean([1.0 if prediction in fallback_predictions else 0.0 for prediction in predictions]),
        "kb_grounding_rate": _safe_mean(
            _has_kb_evidence(item.get("kb_summary")) for item in auto_respond_predictions
        ) if auto_respond_predictions else 0.0,
    }

    for action in ("auto_respond", "route_to_specialist", "escalate_to_human"):
        precision, recall = _precision_recall(actual_actions, predicted_actions, action)
        result[f"{action}_precision"] = precision
        result[f"{action}_recall"] = recall
    escalation_recall = _precision_recall(
        ["escalate" if any(level in {"high", "critical"} for level in labels) else "other"
         for labels in expected_urgency],
        ["escalate" if item == "escalate_to_human" else "other" for item in predicted_actions],
        "escalate",
    )[1]
    result["escalation_recall"] = escalation_recall
    levels = ("low", "medium", "high", "critical")
    result["urgency_confusion_matrix"] = {
        actual: {
            predicted: sum(a == actual and p == predicted for a, p in zip(primary_urgency, predicted_urgency))
            for predicted in levels
        }
        for actual in levels
    }
    result["critical_cases_missed"] = float(sum(
        any(level in {"high", "critical"} for level in expected) and prediction != "escalate_to_human"
        for expected, prediction in zip(expected_urgency, predicted_actions)
    ))

    for field in ("product", "issue_type", "sentiment", "language", "intents"):
        score = _optional_accuracy(predictions, gold, field)
        if score is not None:
            result[f"{field}_accuracy"] = score

    kb_labeled = [
        (prediction, expected["kb_keywords"])
        for prediction, expected in zip(predictions, gold)
        if "kb_keywords" in expected
    ]
    if kb_labeled:
        kb_hits = []
        for prediction, keywords in kb_labeled:
            summary = str(prediction.get("kb_summary") or "").lower()
            has_evidence = _has_kb_evidence(summary)
            if keywords:
                kb_hits.append(has_evidence and any(str(word).lower() in summary for word in keywords))
            else:
                kb_hits.append(not has_evidence)
        result["kb_hit_rate"] = _safe_mean(kb_hits)

    policy_fields = ("urgency", "action", "product", "issue_type", "intents", "confidence")
    policy_checked = [
        prediction
        for prediction in predictions
        if all(field in prediction for field in policy_fields)
    ]
    if policy_checked:
        policy = PolicyGuardrail()
        result["safety_policy_pass_rate"] = _safe_mean(
            not policy.validate(prediction) for prediction in policy_checked
        )

    latencies: list[float] = []
    tool_results: list[bool] = []
    for prediction in predictions:
        if "latency_ms" in prediction:
            latency = prediction["latency_ms"]
            if (
                isinstance(latency, bool)
                or not isinstance(latency, (int, float))
                or not math.isfinite(latency)
                or latency < 0
            ):
                raise ValueError("latency_ms must be a non-negative number.")
            latencies.append(float(latency))
        if "tool_success" in prediction:
            tool_success = prediction["tool_success"]
            if not isinstance(tool_success, bool):
                raise ValueError("tool_success must be a boolean.")
            tool_results.append(tool_success)

    if latencies:
        result["latency_p50_ms"] = _percentile(latencies, 0.50)
        result["latency_p95_ms"] = _percentile(latencies, 0.95)
        result["latency_sample_count"] = float(len(latencies))
    if tool_results:
        result["tool_success_rate"] = _safe_mean(tool_results)
        result["tool_success_sample_count"] = float(len(tool_results))

    for field in ("cost_usd", "llm_calls"):
        values = [float(item[field]) for item in predictions if field in item]
        if values:
            result[f"{field}_p50"] = _percentile(values, 0.50)
            result[f"{field}_p95"] = _percentile(values, 0.95)
            result[f"{field}_sample_count"] = float(len(values))
    if "cost_usd_p50" in result:
        result["projected_daily_cost_usd_p50"] = float(result["cost_usd_p50"]) * 10000

    return result


__all__ = ["accuracy_score", "evaluate_triage"]
