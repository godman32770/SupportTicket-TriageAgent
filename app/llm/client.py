from __future__ import annotations

import json
import os
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, cast

from app.models.triage import TRIAGE_SCHEMA
from app.prompts.templates import build_prompt


#OpenAI LLM CLIENT AND OFFLINE MOCK CLIENT FOR TRIAGE DECISION GENERATION, WITH FALLBACKS
class LLMClient(ABC):
    @abstractmethod
    def generate(self, ticket: Mapping[str, Any], context: Mapping[str, Any]) -> str:
        raise NotImplementedError


class LLMConfigurationError(RuntimeError):
    """A non-retryable live-client configuration error."""


def _contains_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(phrase)}\b", text) for phrase in phrases)


def _infer_urgency(description: str) -> str:
    critical_phrases = (
        "critical",
        "security",
        "breach",
        "security breach",
        "data loss",
        "data breach",
        "outage",
        "service outage",
        "major outage",
        "service down",
        "production down",
        "service unavailable",
        "system-wide outage",
    )
    high_phrases = (
        "urgent",
        "asap",
        "immediately",
        "locked out",
        "can't log in",
        "cannot access",
        "unable to access",
        "business stopped",
        "work is blocked",
    )
    medium_phrases = (
        "billing",
        "payment",
        "refund",
        "error",
        "slow",
        "crash",
        "login",
        "access",
    )

    if _contains_phrase(description, critical_phrases):
        return "critical"
    if _contains_phrase(description, high_phrases):
        return "high"
    if _contains_phrase(description, medium_phrases):
        return "medium"
    return "low"


def _infer_sentiment(description: str, stated_sentiment: object) -> str:
    stated = str(stated_sentiment or "").strip()
    if stated and stated.lower() != "neutral":
        return stated

    for sentiment, phrases in (
        ("angry", ("angry", "furious", "enraged")),
        ("frustrated", ("frustrated", "upset", "annoyed", "disappointed", "unacceptable")),
        ("positive", ("happy", "pleased", "grateful", "thank you", "thanks")),
        ("concerned", ("concerned", "worried")),
    ):
        if _contains_phrase(description, phrases):
            return sentiment
    return "neutral"


INTENT_TAXONOMY = {
    "login": "login_help",
    "billing": "billing_dispute",
    "outage": "service_outage",
    "services": "service_outage",
    "security": "security_threat",
    "legal": "legal_threat",
    "prompt_injection": "prompt_injection",
    "feature_request": "feature_request",
    "bug": "bug_report",
    "general_help": "support_help",
    "support_help": "support_help",
    "bug_report": "bug_report",
    "service_outage": "service_outage",
    "security_threat": "security_threat",
    "billing_dispute": "billing_dispute",
    "login_help": "login_help",
    "legal_threat": "legal_threat",
}


def _resolve_intent(issue_type: str, description: str) -> str:
    key = (issue_type or "").strip().lower()
    if key in INTENT_TAXONOMY:
        return INTENT_TAXONOMY[key]
    if "ignore previous instructions" in description or "prompt injection" in description or "bypass instructions" in description:
        return "prompt_injection"
    if "data breach" in description or "security breach" in description or "customer data" in description:
        return "security_threat"
    if "legal threat" in description or "lawsuit" in description or "legal demand" in description:
        return "legal_threat"
    if "outage" in description or "service unavailable" in description or "down across" in description:
        return "service_outage"
    if "duplicate charge" in description or "charged twice" in description or "refund" in description:
        return "billing_dispute"
    if "password" in description or "login" in description or "lockout" in description:
        return "login_help"
    if "crash" in description or "bug" in description:
        return "bug_report"
    if "feature" in description or "language" in description:
        return "feature_request"
    return "support_help"


class OfflineLLMClient(LLMClient):
    def __init__(self, scripted_responses: dict[str, dict[str, Any]] | None = None):
        self.scripted_responses = scripted_responses or {}

    def generate(self, ticket: Mapping[str, Any], context: Mapping[str, Any]) -> str:
        product = str(ticket.get("product", "")).lower()
        issue = str(ticket.get("issue_type", "")).lower()
        ticket_id = str(ticket.get("ticket_id", ""))
        if ticket_id in self.scripted_responses:
            return json.dumps(self.scripted_responses[ticket_id])

        available_tools = context.get("available_tools", [])
        if "customer_history" in available_tools:
            return json.dumps({"type": "tool_call", "name": "customer_history"})
        if "knowledge_base" in available_tools:
            return json.dumps({"type": "tool_call", "name": "knowledge_base"})
        if "check_service_status" in available_tools and any(
            phrase in str(ticket.get("description", "")).lower()
            for phrase in ("outage", "down", "unavailable", "500", "system inaccessible")
        ):
            return json.dumps({"type": "tool_call", "name": "check_service_status"})

        description = str(ticket.get("description", "")).lower()
        urgency = _infer_urgency(description)
        action = "auto_respond"
        if urgency in {"critical", "high"}:
            action = "escalate_to_human"
        elif urgency == "medium":
            action = "route_to_specialist"

        intent = _resolve_intent(issue, description)

        if "ignore previous instructions" in description or "prompt injection" in description or "bypass instructions" in description or "malicious" in description:
            urgency, action = "high", "escalate_to_human"
            intent = "prompt_injection"
        elif "data breach" in description or "security breach" in description or "customer data" in description:
            urgency, action = "critical", "escalate_to_human"
            intent = "security_threat"
        elif "legal threat" in description or "lawsuit" in description or "legal demand" in description:
            urgency, action = "critical", "escalate_to_human"
            intent = "legal_threat"
        elif "outage" in description or "service unavailable" in description or "platform is down" in description or "api is down" in description or "production is down" in description or "dashboard is down" in description or "down and customer traffic" in description or " is down" in description:
            urgency, action = "critical", "escalate_to_human"
            intent = "service_outage"
        elif issue == "billing" or "duplicate charge" in description or "charged twice" in description or "refund" in description or ("invoice" in description and "billing" in description):
            urgency, action = "medium", "route_to_specialist"
            intent = "billing_dispute"
        elif issue == "bug" or "crash" in description:
            urgency, action = "medium", "route_to_specialist"
            intent = "bug_report"
        elif (issue == "feature_request" or "feature" in description) and "dark mode" not in description and "does not activate" not in description:
            urgency, action = "low", "auto_respond"
            intent = "feature_request"
        elif "dark mode" in description or "does not activate" in description:
            urgency, action = "medium", "route_to_specialist"
            intent = "feature_request"
        elif "locked out" in description or "cannot access" in description or "unable to access" in description or ("urgent" in description and ("login" in description or "access" in description or "account" in description)):
            urgency, action = "high", "escalate_to_human"
            intent = "login_help"
        elif "temporarily disabled" in description or "too many attempts" in description:
            urgency, action = "medium", "route_to_specialist"
            intent = "login_help"
        elif issue == "login" or "password" in description or "login" in description:
            if "urgent" in description or "locked out" in description or "cannot access" in description:
                urgency, action = "high", "escalate_to_human"
            else:
                # A routine password-reset failure is low risk unless the
                # ticket explicitly indicates lockout, urgency, or broader
                # account access failure.
                urgency, action = "low", "auto_respond"
            intent = "login_help"
        elif issue == "general_help" or issue == "support":
            urgency, action = "low", "auto_respond"
            intent = "support_help"

        response = {
            "ticket_id": ticket_id,
            "urgency": urgency,
            "product": product or "unknown",
            "issue_type": issue or "general_support",
            "sentiment": _infer_sentiment(description, ticket.get("sentiment")),
            "language": ticket.get("language", "en"),
            "intents": [intent],
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
        self.timeout_seconds = 30
        self.max_retries = 3
        self.last_usage: dict[str, float] = {}
        self.input_cost_per_million = float(os.getenv("OPENAI_INPUT_COST_PER_MILLION", "0.15"))
        self.output_cost_per_million = float(os.getenv("OPENAI_OUTPUT_COST_PER_MILLION", "0.60"))
        if self.api_key is None:
            raise ValueError("OPENAI_API_KEY is required for live mode.")
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("openai package is not installed.") from exc
        self.client = OpenAI(api_key=self.api_key, timeout=self.timeout_seconds)

    @staticmethod
    def _tools(available_tools: list[str] | None = None) -> list[dict[str, Any]]:
        requested = set(available_tools or ["customer_history", "knowledge_base"])
        tools: list[dict[str, Any]] = []
        if "customer_history" in requested:
            tools.append(
            {
                "type": "function",
                "function": {
                    "name": "get_customer_history",
                    "description": "Fetch the authoritative support history for a customer.",
                    "parameters": {
                        "type": "object",
                        "properties": {"customer_id": {"type": "string"}},
                        "required": ["customer_id"],
                        "additionalProperties": False,
                    },
                },
            },
            )
        if "knowledge_base" in requested:
            tools.append(
                {
                "type": "function",
                "function": {
                    "name": "search_kb",
                    "description": "Search the authoritative knowledge base for this ticket.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "product": {"type": "string"},
                            "issue_type": {"type": "string"},
                        },
                        "required": ["product", "issue_type"],
                        "additionalProperties": False,
                    },
                },
                },
            )
        if "check_service_status" in requested:
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": "check_service_status",
                        "description": "Check the configured service status endpoint for an outage or degradation.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "product": {"type": "string"},
                                "region": {"type": "string"},
                            },
                            "required": ["product"],
                            "additionalProperties": False,
                        },
                    },
                },
            )
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "submit_triage",
                    "description": "Submit the final triage decision after all required context is gathered.",
                    "parameters": {**TRIAGE_SCHEMA},
                },
            },
        )
        return tools

    @staticmethod
    def _retry_after(exc: BaseException) -> float | None:
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", None)
        value = headers.get("retry-after") if headers else None
        try:
            return max(0.0, float(value)) if value is not None else None
        except (TypeError, ValueError):
            return None

    def generate(self, ticket: Mapping[str, Any], context: Mapping[str, Any]) -> str:
        prompt = build_prompt(ticket, context)
        system_prompt = (
            "You are a safe customer support triage assistant. Use the supplied functions for authoritative data. "
            "Never invent customer history or knowledge-base references. Submit the final decision with submit_triage. "
            "`intents` must be an array of strings from the allowed intent taxonomy. `safety_checks` must be an array of strings. "
            "`confidence` must be a float between 0 and 1."
        )

        from openai import OpenAIError

        last_error: BaseException | None = None
        tool_choice: Any = {"type": "function", "function": {"name": "submit_triage"}} if context.get("force_submit") else "auto"
        messages = list(context.get("messages", []))
        if not messages:
            messages = [{"role": "user", "content": prompt}]
        available_tools = context.get("available_tools")
        tool_definitions = self._tools(available_tools if isinstance(available_tools, list) else None)
        for attempt in range(self.max_retries + 1):
            try:
                completion = self.client.chat.completions.create(
                    model=self.model,
                    temperature=0,
                    tools=cast(Any, tool_definitions),
                    tool_choice=tool_choice,
                    messages=[{"role": "system", "content": system_prompt}, *messages],
                )
                usage = getattr(completion, "usage", None)
                self.last_usage = {
                    "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
                    "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
                    "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
                }
                self.last_usage["cost_usd"] = round(
                    self.last_usage["prompt_tokens"] * getattr(self, "input_cost_per_million", 0.15) / 1_000_000
                    + self.last_usage["completion_tokens"] * getattr(self, "output_cost_per_million", 0.60) / 1_000_000,
                    8,
                )
                message = completion.choices[0].message
                calls = getattr(message, "tool_calls", None) or []
                if calls:
                    call = calls[0]
                    name = call.function.name
                    arguments = call.function.arguments or "{}"
                    if name == "submit_triage":
                        return json.dumps({"type": "final", "decision": json.loads(arguments)})
                    aliases = {"get_customer_history": "customer_history", "search_kb": "knowledge_base"}
                    return json.dumps({
                        "type": "tool_call",
                        "name": aliases.get(name, name),
                        "tool_call_id": getattr(call, "id", None) or f"call_{attempt}",
                        "arguments": arguments,
                    })
                return message.content or '{"error": "empty response"}'
            except (OpenAIError, TimeoutError, OSError, ValueError, TypeError) as exc:  # pragma: no cover - live dependency path
                last_error = exc
                error_name = type(exc).__name__
                if error_name in {"AuthenticationError", "PermissionDeniedError", "NotFoundError", "BadRequestError"}:
                    raise LLMConfigurationError(f"OpenAI configuration error: {exc}") from exc
                if isinstance(exc, (ValueError, TypeError)) or attempt >= self.max_retries:
                    raise
                delay = self._retry_after(exc)
                if delay is None:
                    delay = min(8.0, 0.5 * (2**attempt))
                time.sleep(delay)

        if last_error is not None:
            raise last_error
        raise RuntimeError("OpenAI request failed without a specific error.")


__all__ = ["LLMClient", "LLMConfigurationError", "OfflineLLMClient", "OpenAIChatClient"]
