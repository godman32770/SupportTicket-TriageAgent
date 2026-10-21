import pytest

from app.eval.metrics import evaluate_triage


def test_evaluate_triage_measures_extraction_kb_and_safety():
    predictions = [
        {
            "urgency": "low",
            "action": "auto_respond",
            "product": "mobile_app",
            "issue_type": "login",
            "sentiment": "neutral",
            "language": "en",
            "intents": ["login", "password_reset"],
            "confidence": 0.9,
            "kb_summary": "Password reset instructions.",
        },
        {
            "urgency": "critical",
            "action": "escalate_to_human",
            "product": "enterprise",
            "issue_type": "outage",
            "sentiment": "angry",
            "language": "en",
            "intents": ["service_outage"],
            "confidence": 0.95,
            "kb_summary": "No matching KB entries found.",
        },
    ]
    gold = [
        {
            "urgency": "low",
            "action": "auto_respond",
            "product": "mobile_app",
            "issue_type": "login",
            "sentiment": "neutral",
            "language": "en",
            "intents": ["password_reset", "login"],
            "kb_keywords": ["password reset"],
        },
        {
            "urgency": "critical",
            "action": "escalate_to_human",
            "product": "enterprise",
            "issue_type": "outage",
            "sentiment": "angry",
            "language": "en",
            "intents": ["service_outage"],
            "kb_keywords": [],
        },
    ]

    result = evaluate_triage(predictions, gold)

    assert result["product_accuracy"] == 1.0
    assert result["issue_type_accuracy"] == 1.0
    assert result["sentiment_accuracy"] == 1.0
    assert result["language_accuracy"] == 1.0
    assert result["intents_accuracy"] == 1.0
    assert result["kb_grounding_rate"] == 1.0
    assert result["kb_hit_rate"] == 1.0
    assert result["safety_policy_pass_rate"] == 1.0


def test_evaluate_triage_reports_optional_operational_metrics():
    predictions = [
        {"urgency": "low", "action": "route_to_specialist", "latency_ms": 100, "tool_success": True},
        {"urgency": "medium", "action": "route_to_specialist", "latency_ms": 250, "tool_success": False},
    ]
    gold = [
        {"urgency": "low", "action": "route_to_specialist"},
        {"urgency": "medium", "action": "route_to_specialist"},
    ]

    result = evaluate_triage(predictions, gold)

    assert result["latency_p50_ms"] == 100
    assert result["latency_p95_ms"] == 250
    assert result["latency_sample_count"] == 2
    assert result["tool_success_rate"] == 0.5
    assert result["tool_success_sample_count"] == 2


def test_evaluate_triage_rejects_prediction_and_gold_length_mismatch():
    with pytest.raises(ValueError, match="lengths must match"):
        evaluate_triage([{"urgency": "low", "action": "auto_respond"}], [])
