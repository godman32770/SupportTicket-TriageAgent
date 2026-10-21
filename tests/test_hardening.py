from __future__ import annotations

from typing import Any, get_args

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.agent.triage_agent import TriageAgent
from app.guardrails.policy import PolicyGuardrail
from app.llm.client import LLMClient
from app.models.triage import TRIAGE_SCHEMA, TriageDecision
from app.telemetry.redaction import redact_pii
from app.tools import CustomerHistoryTool, KBLookupTool

RISKY_PATTERNS = [
    "security breach",
    "data loss",
    "prompt injection",
    "ignore previous instructions",
    "duplicate charge",
    "service unavailable",
    "billing dispute",
    "lawsuit",
]


@given(st.sampled_from(RISKY_PATTERNS))
def test_guardrail_rules_only_increase_caution(pattern: str) -> None:
    decision = {
        "ticket_id": "T-guard",
        "urgency": "low",
        "product": "web",
        "issue_type": "general_help",
        "sentiment": "neutral",
        "language": "en",
        "intents": ["support_help"],
        "action": "auto_respond",
        "confidence": 0.9,
        "reasoning": pattern,
        "customer_history_summary": "",
        "kb_summary": "No matching KB entries found; use general support workflow.",
        "safety_checks": [],
        "description": pattern,
    }
    issues = PolicyGuardrail().validate({**decision, "description": pattern})
    assert issues, f"Expected a safety issue for risky pattern: {pattern}"
    assert any("auto_respond" in issue.lower() or "escalate" in issue.lower() for issue in issues)


def test_schema_and_pydantic_model_stay_in_sync() -> None:
    model_fields = set(TriageDecision.model_fields)
    schema_fields = set(TRIAGE_SCHEMA["properties"])
    assert model_fields == schema_fields
    assert TRIAGE_SCHEMA["properties"]["urgency"]["enum"] == ["low", "medium", "high", "critical"]
    assert TRIAGE_SCHEMA["properties"]["action"]["enum"] == ["auto_respond", "route_to_specialist", "escalate_to_human"]
    assert get_args(TriageDecision.model_fields["urgency"].annotation) == ("low", "medium", "high", "critical")
    assert get_args(TriageDecision.model_fields["action"].annotation) == ("auto_respond", "route_to_specialist", "escalate_to_human")


def test_failure_modes_are_handled() -> None:
    class TimeoutLLM(LLMClient):
        def generate(self, ticket: dict[str, Any], context: dict[str, Any]) -> str:
            raise TimeoutError("request timed out")

    class MalformedLLM(LLMClient):
        def generate(self, ticket: dict[str, Any], context: dict[str, Any]) -> str:
            return "not valid JSON"

    agent_timeout = TriageAgent(llm_client=TimeoutLLM())
    agent_malformed = TriageAgent(llm_client=MalformedLLM())

    timeout_result = agent_timeout.run({
        "ticket_id": "T-timeout",
        "customer_id": "C-100",
        "product": "web",
        "issue_type": "general_help",
        "description": "I need help with an order.",
    })
    malformed_result = agent_malformed.run({
        "ticket_id": "T-malformed",
        "customer_id": "C-200",
        "product": "web",
        "issue_type": "general_help",
        "description": "I need help with an order.",
    })

    assert timeout_result.action == "escalate_to_human"
    assert malformed_result.action == "escalate_to_human"

    tool_registry = agent_timeout.tool_registry
    with pytest.raises(ValueError):
        tool_registry.execute({"customer_id": "C-100"}, "missing_tool")

    history_tool = CustomerHistoryTool(fail_on_fetch=True)
    assert history_tool.fetch("C-100").success is False

    kb_tool = KBLookupTool(fail_on_lookup=True)
    assert kb_tool.lookup("web", "billing").success is False


def test_redaction_masks_thai_ids_and_cards() -> None:
    text = "Customer called 0812345678, ID 1234567890123, card 4111 1111 1111 1111."
    redacted = redact_pii(text)
    assert "[TH_PHONE]" in redacted
    assert "[NATIONAL_ID]" in redacted
    assert "[CARD]" in redacted
