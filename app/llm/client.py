from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from app.prompts.templates import build_prompt

#OpenAI LLM CLIENT AND OFFLINE MOCK CLIENT FOR TRIAGE DECISION GENERATION, WITH FALLBACKS
class LLMClient(ABC):
    @abstractmethod
    def generate(self, ticket: Mapping[str, Any], context: Mapping[str, Any]) -> str:
        raise NotImplementedError


class OfflineLLMClient(LLMClient):
    def __init__(self, scripted_responses: dict[str, dict[str, Any]] | None = None):
        self.scripted_responses = scripted_responses or {}

    def generate(self, ticket: Mapping[str, Any], context: Mapping[str, Any]) -> str:
        product = str(ticket.get("product", "")).lower()
        issue = str(ticket.get("issue_type", "")).lower()
        ticket_id = str(ticket.get("ticket_id", ""))
        if ticket_id in self.scripted_responses:
            return json.dumps(self.scripted_responses[ticket_id])

        urgency = "low"
        action = "auto_respond"
        description = str(ticket.get("description", "")).lower()
        if any(token in description for token in ["critical", "data loss", "security", "outage", "urgent"]):
            urgency = "critical"
            action = "escalate_to_human"
        elif any(token in description for token in ["cannot login", "billing", "payment", "refund", "error", "slow"]):
            urgency = "medium"
            action = "route_to_specialist"
        elif any(token in description for token in ["unable to access", "crash"]):
            urgency = "high"
            action = "route_to_specialist"

        response = {
            "ticket_id": ticket_id,
            "urgency": urgency,
            "product": product or "unknown",
            "issue_type": issue or "general_support",
            "sentiment": "frustrated" if "angry" in description else "neutral",
            "language": ticket.get("language", "en"),
            "intents": [issue or "support_help"],
            "action": action,
            "confidence": 0.9,
            "reasoning": "Offline triage selected a safe classification using rule-based severity heuristics and the supplied history/KB context.",
            "customer_history_summary": str(context.get("customer_history", "")),
            "kb_summary": str(context.get("kb", "")),
            "safety_checks": ["urgency in allowed set", "action matches policy"],
        }
        return json.dumps(response)


class OpenAIChatClient(LLMClient):
    def __init__(self, api_key: str | None = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        if self.api_key is None:
            raise ValueError("OPENAI_API_KEY is required for live mode.")
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("openai package is not installed.") from exc
        self.client = OpenAI(api_key=self.api_key)

    def generate(self, ticket: Mapping[str, Any], context: Mapping[str, Any]) -> str:
        prompt = build_prompt(ticket, context)
        completion = self.client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are a safe customer support triage assistant. Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
        )
        return completion.choices[0].message.content or '{"error": "empty response"}'


__all__ = ["LLMClient", "OfflineLLMClient", "OpenAIChatClient"]
