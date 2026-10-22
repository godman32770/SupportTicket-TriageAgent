import pytest

from app.guardrails.policy import PolicyGuardrail


def make_decision(**kwargs):
    base = {
        "ticket_id": "T-X",
        "urgency": "medium",
        "product": "mobile_app",
        "issue_type": "general",
        "sentiment": "neutral",
        "language": "en",
        "intents": ["support_help"],
        "action": "auto_respond",
        "confidence": 0.9,
        "reasoning": "",
        "customer_history_summary": "",
        "kb_summary": "KB article about password reset.",
        "safety_checks": [],
    }
    base.update(kwargs)
    return base


@pytest.mark.parametrize(
    ("decision", "expected_fragment"),
    [
        (make_decision(issue_type="billing", action="auto_respond", customer_history_summary="2 unresolved payments"), "billing"),
        (make_decision(product="enterprise-suite", issue_type="outage", action="route_to_specialist", urgency="high"), "enterprise"),
        (make_decision(issue_type="security", action="auto_respond", urgency="medium"), "security"),
        (make_decision(issue_type="legal", action="auto_respond", urgency="medium"), "security"),
        (make_decision(action="auto_respond", safety_checks=["prompt_injection"], kb_summary="KB article about password reset."), "prompt"),
        (make_decision(action="auto_respond", kb_summary="", confidence=0.9), "kb"),
        (make_decision(action="auto_respond", confidence=0.6), "confidence"),
        (make_decision(intents=["human_escalation"], action="auto_respond", kb_summary="KB article about password reset."), "intent"),
        (make_decision(action="auto_respond", reasoning="I can offer a refund immediately", kb_summary="KB article about refund process."), "refund"),
        (make_decision(action="auto_respond", reasoning="The customer is locked out and cannot access the account."), "account_access"),
    ],
)
def test_guardrail_rules_trigger(decision, expected_fragment):
    issues = PolicyGuardrail().validate(decision)
    assert issues
    assert any(expected_fragment in issue.lower() for issue in issues)
