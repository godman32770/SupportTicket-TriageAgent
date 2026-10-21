import json

from app.agent.triage_agent import TriageAgent, build_safe_fallback
from app.cli.main import main
from app.llm.client import LLMClient
from app.models import normalize_ticket


def test_cli_accepts_ticket_arrays(tmp_path, capsys):
    batch = [
        {
            "ticket_id": "T-100",
            "customer_id": "C-1",
            "product": "mobile_app",
            "issue_type": "login",
            "description": "Need to reset my password.",
        },
        {
            "ticket_id": "T-101",
            "customer_id": "C-2",
            "product": "web",
            "issue_type": "billing",
            "description": "I have a duplicate charge.",
        },
    ]
    path = tmp_path / "tickets.json"
    path.write_text(json.dumps(batch), encoding="utf-8")

    exit_code = main(["--ticket-file", str(path), "--mode", "offline"])

    assert exit_code == 0
    stdout = capsys.readouterr().out
    payload = json.loads(stdout)
    assert len(payload) == 2
    assert {item["ticket_id"] for item in payload} == {"T-100", "T-101"}


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


def test_ordinary_invalid_output_falls_back_to_safe_human_escalation():
    class InvalidOutputClient(LLMClient):
        calls = 0

        def generate(self, ticket, context):
            self.calls += 1
            return "not valid JSON"

    client = InvalidOutputClient()
    agent = TriageAgent(llm_client=client)
    result = agent.run({
        "ticket_id": "T-44",
        "customer_id": "C-404",
        "product": "profile",
        "issue_type": "general question",
        "description": "How can I change my profile photo?",
    })

    assert result.urgency == "high"
    assert result.action == "escalate_to_human"
    assert client.calls == 3
