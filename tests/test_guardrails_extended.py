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
        "kb_summary": "",
        "safety_checks": [],
    }
    base.update(kwargs)
    return base


def test_billing_no_auto():
    policy = PolicyGuardrail()
    # simulate billing dispute and unresolved payments in history
    d = make_decision(issue_type="billing", action="auto_respond", customer_history_summary="2 unresolved payments")
    issues = policy.validate(d)
    assert any("billing" in s.lower() or "chargeback" in s.lower() for s in issues)


def test_kb_required_for_auto_respond():
    policy = PolicyGuardrail()
    d = make_decision(issue_type="login", action="auto_respond", kb_summary="")
    issues = policy.validate(d)
    assert any("kb" in s.lower() or "knowledge" in s.lower() for s in issues)


def test_low_confidence_escalate():
    policy = PolicyGuardrail()
    d = make_decision(action="auto_respond", confidence=0.6)
    issues = policy.validate(d)
    assert any("confidence" in s.lower() for s in issues)


def test_sec_escalate():
    policy = PolicyGuardrail()
    d = make_decision(issue_type="security", action="auto_respond", urgency="medium")
    issues = policy.validate(d)
    assert any("security" in s.lower() or "critical" in s.lower() for s in issues)


def test_enterprise_outage_escalate():
    policy = PolicyGuardrail()
    d = make_decision(product="enterprise-suite", issue_type="outage", action="route_to_specialist", urgency="high")
    issues = policy.validate(d)
    assert any("enterprise" in s.lower() or "outage" in s.lower() for s in issues)
