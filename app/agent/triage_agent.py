from __future__ import annotations

import json
import logging
import time
from collections.abc import Mapping
from typing import Any

from app.guardrails.policy import PolicyGuardrail
from app.guardrails.schema_validator import SchemaValidator
from app.llm.client import LLMClient, LLMConfigurationError, OfflineLLMClient, OpenAIChatClient
from app.models import normalize_ticket
from app.models.triage import SupportTicket, TriageDecision
from app.telemetry.metrics import TelemetryEvent, TelemetryRecorder
from app.telemetry.redaction import redact_pii
from app.tools import CustomerHistoryTool, KBLookupTool, ToolResult

logger = logging.getLogger(__name__)


class ToolSpec:
    def __init__(self, name: str, description: str, executor: Any) -> None:
        self.name = name
        self.description = description
        self.executor = executor


class ToolRegistry:
    def __init__(self, customer_tool: CustomerHistoryTool, kb_tool: KBLookupTool) -> None:
        self._tools = {
            "customer_history": ToolSpec(
                "customer_history",
                "Fetch prior customer support history for the customer_id.",
                lambda ticket: customer_tool.fetch(str(ticket.get("customer_id", ""))),
            ),
            "knowledge_base": ToolSpec(
                "knowledge_base",
                "Look up issue-specific knowledge-base guidance for the product and issue type.",
                self._lookup_kb,
            ),
        }
        self._kb_tool = kb_tool

    def _lookup_kb(self, ticket: Mapping[str, Any]) -> ToolResult:
        product = str(ticket.get("product", ""))
        issue_type = str(ticket.get("issue_type", ""))
        description = str(ticket.get("description", ""))
        try:
            return self._kb_tool.lookup(product, issue_type, description)
        except TypeError:
            # Preserve compatibility with injected test/integration tools that
            # implement the original two-argument lookup contract.
            return self._kb_tool.lookup(product, issue_type)

    def available(self) -> list[str]:
        return list(self._tools)

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def execute(self, ticket: Mapping[str, Any], name: str) -> Any:
        spec = self.get(name)
        if spec is None:
            raise ValueError(f"Unknown tool: {name}")
        return spec.executor(ticket)

#CLASSIFy URGENCY, EXTRACT FIELDS, DECIDE ACTION, REASON SAFELY, RETURN JSON ONLY

def build_safe_fallback(ticket: SupportTicket, history: str, kb: str) -> dict[str, Any]:
    description = (ticket.description or "").lower()
    text = f"{description} {ticket.issue_type or ''}".lower()

    critical_tokens = ("security", "breach", "data loss", "outage", "down", "legal", "urgent")
    urgency = "critical" if any(token in text for token in critical_tokens) else "high"
    action = "escalate_to_human"

    intent_map = {
        "login": "login_help",
        "billing": "billing_dispute",
        "outage": "service_outage",
        "services": "service_outage",
        "security": "security_threat",
        "legal": "legal_threat",
        "bug": "bug_report",
        "feature_request": "feature_request",
        "general_help": "support_help",
        "prompt_injection": "prompt_injection",
    }
    issue_key = (ticket.issue_type or "general_help").strip().lower()
    fallback_intent = intent_map.get(issue_key, "support_help")

    return {
        "ticket_id": ticket.ticket_id,
        "urgency": urgency,
        "product": ticket.product,
        "issue_type": ticket.issue_type,
        "sentiment": ticket.sentiment or "neutral",
        "language": ticket.language or "en",
        "intents": [fallback_intent],
        "action": action,
        "confidence": 0.0,
        "reasoning": "Fallback triggered because the model output, tool context, or policy check was invalid or unsafe; the system escalated to a human for safety.",
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
        max_model_retries: int = 2,
        max_tool_calls: int = 2,
    ) -> None:
        if max_model_retries < 0:
            raise ValueError("max_model_retries must be non-negative.")
        if max_tool_calls < 0:
            raise ValueError("max_tool_calls must be non-negative.")
        self.mode = mode
        self.customer_tool = customer_tool or CustomerHistoryTool()
        self.kb_tool = kb_tool or KBLookupTool()
        self.api_key = api_key
        self.model = model
        self.max_model_retries = max_model_retries
        self.max_tool_calls = max_tool_calls
        self.llm_client = llm_client or self._build_llm_client()
        self.tool_registry = ToolRegistry(self.customer_tool, self.kb_tool)
        self.policy_guardrail = PolicyGuardrail()
        self.schema_validator = SchemaValidator()
        self.telemetry = TelemetryRecorder()
        self.last_run_metrics: dict[str, Any] = {}

    def _build_llm_client(self) -> LLMClient:
        if self.mode == "live":
            return OpenAIChatClient(api_key=self.api_key, model=self.model)
        return OfflineLLMClient()

    def _record_event(self, event: str, ticket_id: str | None, **kwargs: Any) -> None:
        self.telemetry.record(TelemetryEvent(event=event, ticket_id=ticket_id, **kwargs))

    def _normalize_aliases(self, response: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(response)

        issue_type = str(normalized.get("issue_type", "")).strip().lower()
        if issue_type in {"settings", "settings_question", "general_help", "support"}:
            normalized["issue_type"] = "general_help"

        intents = normalized.get("intents")
        if isinstance(intents, list):
            mapped: list[str] = []
            alias_map = {
                "settings_question": "support_help",
                "settings": "support_help",
                "general_question": "support_help",
                "account_help": "support_help",
                "security_issue": "security_threat",
                "report_outage": "service_outage",
                "request_assistance": "support_help",
                "request_help": "support_help",
                "bug": "bug_report",
                "feature": "feature_request",
                "billing_question": "billing_dispute",
            }
            for intent in intents:
                key = str(intent).strip().lower()
                mapped.append(alias_map.get(key, key))
            normalized["intents"] = mapped

        return normalized

    def _parse_llm_response(self, output: str) -> dict[str, Any]:
        try:
            parsed = json.loads(output)
        except json.JSONDecodeError:
            return {"error": "invalid_json"}

        if not isinstance(parsed, dict):
            return {"error": "response_must_be_json_object"}
        if parsed.get("type") == "tool_call":
            name = parsed.get("name")
            if (
                set(parsed) != {"type", "name"}
                or not isinstance(name, str)
                or name not in {"customer_history", "knowledge_base", "get_customer_history", "search_kb"}
            ):
                return {"error": "invalid_tool_call"}
            aliases = {"get_customer_history": "customer_history", "search_kb": "knowledge_base"}
            parsed["name"] = aliases.get(parsed["name"], parsed["name"])
            return parsed
        if parsed.get("type") == "final":
            decision = parsed.get("decision")
            if not isinstance(decision, dict) or set(parsed) != {"type", "decision"}:
                return {"error": "invalid_final_decision"}
            return self._normalize_aliases(decision)
        # Accept the original direct-decision format for injected clients and integrations.
        return self._normalize_aliases(parsed)

    def run(self, ticket_payload: Mapping[str, Any] | str) -> TriageDecision:
        started = time.perf_counter()
        ticket = normalize_ticket(ticket_payload)
        ticket_data = ticket.model_dump(mode="json", exclude_none=True)
        context: dict[str, Any] = {
            "available_tools": ["customer_history", "knowledge_base"],
            "feedback": [],
            "tool_trace": [],
        }
        used_tools: set[str] = set()
        tool_calls = 0
        llm_calls = 0
        retries = 0
        decision: dict[str, Any] | None = None

        while retries <= self.max_model_retries:
            context["available_tools"] = [
                name for name in self.tool_registry.available() if name not in used_tools
            ]
            context["force_submit"] = (
                context.get("force_submit_next", False)
                or tool_calls >= self.max_tool_calls
                or not context["available_tools"]
            )
            try:
                llm_calls += 1
                raw = self.llm_client.generate(ticket_data, context)
            except LLMConfigurationError:
                raise
            except (RuntimeError, OSError, TimeoutError, ValueError, TypeError) as exc:
                safe_msg = redact_pii(str(exc))
                logger.warning("LLM generation failed for ticket %s: %s", ticket.ticket_id, safe_msg)
                self._record_event("llm_error", ticket.ticket_id, metadata={"error": safe_msg})
                context["feedback"] = [f"Model generation failed: {type(exc).__name__}."]
                break

            response = self._parse_llm_response(raw)
            if "error" in response:
                retries += 1
                safe_err = redact_pii(str(response["error"]))
                logger.warning("Model responded with parse error for ticket %s: %s", ticket.ticket_id, safe_err)
                self._record_event("parse_error", ticket.ticket_id, metadata={"error": safe_err})
                context["feedback"] = [response["error"]]
                context["tool_trace"].append({"event": "invalid_model_response", "error": response["error"]})
                context["force_submit_next"] = True
                continue

            if response.get("type") == "tool_call":
                tool_name = response["name"]
                if tool_name in used_tools or tool_calls >= self.max_tool_calls:
                    retries += 1
                    logger.warning("Tool request rejected for %s: already used or over limit", tool_name)
                    context["feedback"] = [
                        "Tool request unavailable: each available tool may be called once, up to the tool-call limit."
                    ]
                    context["tool_trace"].append({"event": "rejected_tool_call", "tool": tool_name})
                    context["force_submit_next"] = True
                    continue

                used_tools.add(tool_name)
                tool_calls += 1
                context["tool_trace"].append({"event": "tool_call", "tool": tool_name})
                try:
                    result = self.tool_registry.execute(ticket_data, tool_name)
                    if tool_name == "customer_history":
                        context["customer_history"] = result.summary
                    else:
                        context["kb"] = result.summary
                    if not result.success:
                        logger.warning("Tool %s failed for ticket %s: %s", tool_name, ticket.ticket_id, result.error)
                        context["feedback"] = [
                            f"{tool_name} tool reported failure: {result.error or 'no details provided'}."
                        ]
                        context["tool_trace"].append({"event": "tool_error", "tool": tool_name})
                        retries += 1
                    else:
                        context["feedback"] = []
                        context["tool_trace"].append({"event": "tool_result", "tool": tool_name, "status": "success"})
                except (RuntimeError, ValueError, TypeError, OSError) as exc:
                    context[tool_name if tool_name == "customer_history" else "kb"] = (
                        f"{tool_name.replace('_', ' ').title()} lookup unavailable."
                    )
                    logger.exception("Tool execution crashed for %s on ticket %s", tool_name, ticket.ticket_id)
                    context["feedback"] = [f"{tool_name} tool failed: {type(exc).__name__}."]
                    context["tool_trace"].append({"event": "tool_error", "tool": tool_name})
                    retries += 1
                continue

            response["ticket_id"] = ticket.ticket_id
            response["customer_history_summary"] = str(context.get("customer_history", ""))
            response["kb_summary"] = str(context.get("kb", ""))
            schema_issues = self.schema_validator.validate(response)
            guardrail_issues = (
                self.policy_guardrail.validate({**response, "description": ticket.description}) if not schema_issues else []
            )
            if not schema_issues and not guardrail_issues:
                decision = response
                logger.info("Accepted triage decision for ticket %s", ticket.ticket_id)
                break

            retries += 1
            logger.warning("Decision rejected for ticket %s: schema=%s guardrails=%s", ticket.ticket_id, schema_issues, guardrail_issues)
            context["feedback"] = schema_issues + guardrail_issues

        if decision is None:
            decision = build_safe_fallback(
                ticket,
                str(context.get("customer_history", "Customer history was not requested.")),
                str(context.get("kb", "Knowledge base was not requested.")),
            )
            schema_issues = self.schema_validator.validate(decision)
            guardrail_issues = self.policy_guardrail.validate({**decision, "description": ticket.description})
            logger.warning("Fallback decision used for ticket %s: schema=%s guardrails=%s", ticket.ticket_id, schema_issues, guardrail_issues)

        if schema_issues or guardrail_issues:
            logger.warning(
                "Final fallback for ticket %s still produced issues: schema=%s guardrails=%s; returning safe escalation.",
                ticket.ticket_id,
                schema_issues,
                guardrail_issues,
            )
            decision = {
                **decision,
                "ticket_id": ticket.ticket_id,
                "urgency": "critical",
                "action": "escalate_to_human",
                "intents": ["support_help"],
                "confidence": 0.0,
                "reasoning": "Safety fallback escalated this ticket because the generated fallback did not pass validation.",
                "customer_history_summary": str(context.get("customer_history", "")),
                "kb_summary": str(context.get("kb", "")),
                "safety_checks": ["fallback guardrail applied", "forced human escalation"],
            }

        result = TriageDecision.model_validate(decision)
        usage = getattr(self.llm_client, "last_usage", {})
        self.last_run_metrics = {
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "prompt_tokens": int(usage.get("prompt_tokens", 0)),
            "completion_tokens": int(usage.get("completion_tokens", 0)),
            "total_tokens": int(usage.get("total_tokens", 0)),
            "tool_calls": tool_calls,
            "llm_calls": llm_calls,
            "cost_usd": float(usage.get("cost_usd", 0.0)),
            "projected_daily_cost_usd": round(float(usage.get("cost_usd", 0.0)) * 10000, 6),
        }
        return result


__all__ = ["TriageAgent", "build_safe_fallback"]
