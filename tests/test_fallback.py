import json

from app.models import normalize_ticket
from app.agent.triage_agent import build_safe_fallback


def test_normalize_ticket_from_dict():
    ticket = normalize_ticket({
        "ticket_id": "T-42",
        "customer_id": "C-100",
        "product": "mobile_app",
        "issue_type": "login",
        "description": "Cannot log in after password reset.",
    })
    assert ticket.ticket_id == "T-42"
    assert ticket.product == "mobile_app"


def test_safe_fallback_is_consistent():
    ticket = normalize_ticket(json.dumps({
        "ticket_id": "T-43",
        "customer_id": "C-200",
        "product": "web",
        "issue_type": "security",
        "description": "URGENT security breach with data loss.",
    }))
    result = build_safe_fallback(ticket, "history", "kb")
    assert result["action"] == "escalate_to_human"
    assert result["urgency"] == "critical"
