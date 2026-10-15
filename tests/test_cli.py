from app.agent.triage_agent import TriageAgent


def test_agent_invalid_output_falls_back_to_safe_response():
    agent = TriageAgent(mode="offline")
    result = agent.run({
        "ticket_id": "T-01",
        "customer_id": "C-100",
        "product": "mobile_app",
        "issue_type": "login",
        "description": "I cannot access my account and it is urgent.",
        "language": "en",
        "sentiment": "frustrated",
    })
    assert result.action in {"auto_respond", "route_to_specialist", "escalate_to_human"}
    assert result.ticket_id == "T-01"
