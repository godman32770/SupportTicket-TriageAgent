import pytest

from app.agent.triage_agent import TriageAgent
from tests.test_orchestration import SequenceClient, _decision


@pytest.mark.parametrize("description", [
    "The Zapier webhook integration stopped working and payloads are empty.",
    "The app is unusable with NVDA because buttons have no ARIA labels.",
    "The dashboard takes 40 seconds to load and reports time out for everyone.",
])
def test_specialist_signals_route_to_specialist(description):
    result = TriageAgent(llm_client=SequenceClient([{"type": "final", "decision": _decision()}])).run({
        "ticket_id": "T-specialist",
        "customer_id": "C-specialist",
        "product": "support_platform",
        "issue_type": "general_help",
        "description": description,
    })
    assert result.action == "route_to_specialist"


def test_organization_wide_lockout_is_critical():
    result = TriageAgent(llm_client=SequenceClient([{"type": "final", "decision": _decision()}])).run({
        "ticket_id": "T-org-lockout",
        "customer_id": "C-org-lockout",
        "product": "support_platform",
        "issue_type": "general_help",
        "description": "Our entire organization is locked out and all employees cannot access critical workflows.",
    })
    assert result.urgency == "critical"
    assert result.action == "escalate_to_human"
