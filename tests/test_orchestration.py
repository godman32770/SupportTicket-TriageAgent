import json

import pytest

from app.agent.triage_agent import TriageAgent
from app.llm.client import LLMClient
from app.tools import ToolResult


def _decision():
    return {
        "ticket_id": "T-60",
        "urgency": "medium",
        "product": "account",
        "issue_type": "settings",
        "sentiment": "neutral",
        "language": "en",
        "intents": ["settings_question"],
        "action": "route_to_specialist",
        "confidence": 0.9,
        "reasoning": "The customer needs help with account settings.",
        "customer_history_summary": "No prior customer history.",
        "kb_summary": "Settings guide found.",
        "safety_checks": [],
    }


class SequenceClient(LLMClient):
    def __init__(self, responses):
        self.responses = iter(responses)
        self.contexts = []

    def generate(self, ticket, context):
        self.contexts.append(dict(context))
        return json.dumps(next(self.responses))


class CustomerHistorySpy:
    def __init__(self):
        self.calls = 0

    def fetch(self, customer_id):
        self.calls += 1
        return ToolResult(success=True, summary=f"History for {customer_id}")


class KBLookupSpy:
    def __init__(self):
        self.calls = []

    def lookup(self, product, issue_type):
        self.calls.append((product, issue_type))
        return ToolResult(success=True, summary="Settings guide found.")


def test_orchestrator_runs_only_the_requested_tool():
    client = SequenceClient([
        {"type": "tool_call", "name": "knowledge_base"},
        {"type": "final", "decision": _decision()},
    ])
    history_tool = CustomerHistorySpy()
    kb_tool = KBLookupSpy()

    result = TriageAgent(
        llm_client=client,
        customer_tool=history_tool,
        kb_tool=kb_tool,
    ).run({
        "ticket_id": "T-60",
        "customer_id": "C-60",
        "product": "account",
        "issue_type": "settings",
        "description": "How do I update my account settings?",
    })

    assert result.ticket_id == "T-60"
    assert history_tool.calls == 0
    assert kb_tool.calls == [("account", "settings")]
    assert "knowledge_base" not in client.contexts[1]["available_tools"]
    assert client.contexts[1]["kb"] == "Settings guide found."


def test_ticket_metadata_is_owned_by_application():
    wrong = _decision()
    wrong.update({"product": "Safe", "issue_type": "service outage", "language": "en", "sentiment": "neutral"})
    client = SequenceClient([{"type": "final", "decision": wrong}])

    result = TriageAgent(llm_client=client).run({
        "ticket_id": "T-60",
        "customer_id": "C-60",
        "product": "web_app",
        "issue_type": "appearance_settings",
        "description": "The dark mode setting does not activate.",
        "language": "th",
        "sentiment": "frustrated",
    })

    assert result.product == "web_app"
    assert result.issue_type == "appearance_settings"
    assert result.language == "th"
    assert result.sentiment == "frustrated"


def test_orchestrator_retries_invalid_decision_with_validation_feedback():
    invalid = _decision()
    invalid["urgency"] = "urgent"
    client = SequenceClient([
        {"type": "final", "decision": invalid},
        {"type": "final", "decision": _decision()},
    ])

    result = TriageAgent(
        llm_client=client,
        max_model_retries=1,
    ).run({
        "ticket_id": "T-60",
        "customer_id": "C-60",
        "product": "account",
        "issue_type": "settings",
        "description": "How do I update my account settings?",
    })

    assert result.urgency == "medium"
    assert len(client.contexts) == 2
    assert client.contexts[1]["feedback"]


def test_orchestrator_does_not_repeat_a_tool_request():
    client = SequenceClient([
        {"type": "tool_call", "name": "customer_history"},
        {"type": "tool_call", "name": "customer_history"},
        {"type": "final", "decision": _decision()},
    ])
    history_tool = CustomerHistorySpy()

    result = TriageAgent(
        llm_client=client,
        customer_tool=history_tool,
        max_model_retries=1,
    ).run({
        "ticket_id": "T-60",
        "customer_id": "C-60",
        "product": "account",
        "issue_type": "settings",
        "description": "How do I update my account settings?",
    })

    assert result.ticket_id == "T-60"
    assert history_tool.calls == 1
    assert client.contexts[2]["feedback"]


def test_orchestrator_retries_malformed_tool_name():
    client = SequenceClient([
        {"type": "tool_call", "name": []},
        {"type": "final", "decision": _decision()},
    ])

    result = TriageAgent(llm_client=client, max_model_retries=1).run({
        "ticket_id": "T-60",
        "customer_id": "C-60",
        "product": "account",
        "issue_type": "settings",
        "description": "How do I update my account settings?",
    })

    assert result.ticket_id == "T-60"
    assert client.contexts[1]["feedback"] == ["invalid_tool_call"]


def test_tool_registry_lists_supported_tools():
    agent = TriageAgent(llm_client=SequenceClient([{"type": "final", "decision": _decision()}]))
    assert agent.tool_registry.available() == ["customer_history", "knowledge_base", "check_service_status"]
    assert agent.tool_registry.get("customer_history").name == "customer_history"


def test_orchestrator_rejects_negative_iteration_limits():
    with pytest.raises(ValueError, match="max_model_retries"):
        TriageAgent(max_model_retries=-1)

    with pytest.raises(ValueError, match="max_tool_calls"):
        TriageAgent(max_tool_calls=-1)
