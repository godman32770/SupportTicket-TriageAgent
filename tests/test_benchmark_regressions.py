from app.agent.triage_agent import TriageAgent
from tests.test_orchestration import SequenceClient, _decision


def test_payroll_upload_outage_is_not_misclassified_as_performance_specialist_case():
    result = TriageAgent(llm_client=SequenceClient([{"type": "final", "decision": _decision()}])).run({
        "ticket_id": "T318",
        "customer_id": "C318",
        "product": "support_platform",
        "issue_type": "general_help",
        "description": "We cannot complete payroll uploads because the platform is unavailable.",
    })
    assert result.urgency == "high"
    assert result.action == "escalate_to_human"
