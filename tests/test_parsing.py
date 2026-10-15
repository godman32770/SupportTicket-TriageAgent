from app.guardrails.policy import PolicyGuardrail


def test_guardrail_accepts_valid_decision():
    policy = PolicyGuardrail()
    result = policy.validate({
        "urgency": "medium",
        "action": "route_to_specialist",
        "product": "mobile_app",
        "issue_type": "login",
        "intents": ["login_issue"],
        "confidence": 0.89,
    })
    assert result == []


def test_guardrail_rejects_unsafe_decision():
    policy = PolicyGuardrail()
    result = policy.validate({
        "urgency": "critical",
        "action": "auto_respond",
        "product": "mobile_app",
        "issue_type": "security",
        "intents": ["security_breach"],
        "confidence": 0.95,
    })
    assert any("critical" in issue.lower() or "high-risk" in issue.lower() for issue in result)
