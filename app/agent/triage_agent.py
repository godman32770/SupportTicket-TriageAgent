from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from app.guardrails.policy import PolicyGuardrail
from app.guardrails.schema_validator import SchemaValidator
from app.llm.client import LLMClient, OfflineLLMClient, OpenAIChatClient
from app.models import normalize_ticket
from app.models.triage import SupportTicket, TriageDecision
from app.tools import CustomerHistoryTool, KBLookupTool

#CLASSIFy URGENCY, EXTRACT FIELDS, DECIDE ACTION, REASON SAFELY, RETURN JSON ONLY

def build_safe_fallback(ticket: SupportTicket, history: str, kb: str) -> dict[str, Any]:
    description = (ticket.description or "").lower()
    urgency = "low"
    action = "auto_respond"

    if any(token in description for token in ["security", "critical", "data loss", "outage", "breach", "urgent"]):
        urgency = "critical"
        action = "escalate_to_human"
    elif any(token in description for token in ["billing", "payment", "refund", "login", "crash", "slow", "error", "cannot access"]):
        urgency = "medium"
        action = "route_to_specialist"
    elif any(token in description for token in ["help", "question", "bug"]):
        urgency = "high"
        action = "route_to_specialist"
    #fallback to low urgency and auto_respond if no keywords match
    return {
        "ticket_id": ticket.ticket_id,
        "urgency": urgency,
        "product": ticket.product,
        "issue_type": ticket.issue_type,
        "sentiment": ticket.sentiment or "neutral",
        "language": ticket.language or "en",
        "intents": [ticket.issue_type or "support_help"],
        "action": action,
        "confidence": 0.65,
        "reasoning": "Fallback triggered because the model output or tool context was invalid or unsafe.",
        "customer_history_summary": history,
        "kb_summary": kb,
        "safety_checks": ["fallback guardrail applied"],
    }


class TriageAgent:
    def __init__(
        self,
        mode: str = "offline",
        customer_tool: CustomerHistoryTool | None = None,
        kb_tool: KBLookupTool | None = None,
        llm_client: LLMClient | None = None,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
    ) -> None:
        self.mode = mode
        self.customer_tool = customer_tool or CustomerHistoryTool()
        self.kb_tool = kb_tool or KBLookupTool()
        self.api_key = api_key
        self.model = model
        self.llm_client = llm_client or self._build_llm_client()
        self.policy_guardrail = PolicyGuardrail()
        self.schema_validator = SchemaValidator()

    def _build_llm_client(self) -> LLMClient:
        if self.mode == "live":
            return OpenAIChatClient(api_key=self.api_key, model=self.model)
        return OfflineLLMClient()

    def _parse_llm_response(self, output: str) -> dict[str, Any]:
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return {"error": "invalid_json"}
#LOOK UP CUSTOMER HISTORY AND KB ENTRIES, CALL LLM, VALIDATE OUTPUT, FALLBACK IF INVALID OR UNSAFE FROM init.py in tools
    def run(self, ticket_payload: Mapping[str, Any] | str) -> TriageDecision:
        ticket = normalize_ticket(ticket_payload)
        history = self.customer_tool.fetch(ticket.customer_id)
        kb = self.kb_tool.lookup(ticket.product, ticket.issue_type)
        context = {"customer_history": history.summary, "kb": kb.summary}

        try:
            raw = self.llm_client.generate(ticket.model_dump(mode="json", exclude_none=True), context)
        except Exception:
            raw = json.dumps(build_safe_fallback(ticket, history.summary, kb.summary))

        decision = self._parse_llm_response(raw)
        if not isinstance(decision, dict) or "error" in decision:
            decision = build_safe_fallback(ticket, history.summary, kb.summary)

        schema_issues = self.schema_validator.validate(decision)
        guardrail_issues = self.policy_guardrail.validate(decision)

        if schema_issues or guardrail_issues:
            decision = build_safe_fallback(ticket, history.summary, kb.summary)
            schema_issues = self.schema_validator.validate(decision)
            guardrail_issues = self.policy_guardrail.validate(decision)

        if schema_issues or guardrail_issues:
            raise ValueError("; ".join(schema_issues + guardrail_issues))

        return TriageDecision.model_validate(decision)


__all__ = ["TriageAgent", "build_safe_fallback"]
