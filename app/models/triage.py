from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Urgency = Literal["low", "medium", "high", "critical"]
Action = Literal["auto_respond", "route_to_specialist", "escalate_to_human"]

#DATA STRUCTURE FOR SUPPORT TICKET AND TRIAGE DECISION, WITH VALIDATION AND FALLBACK LOGIC
class SupportTicket(BaseModel):
    ticket_id: str
    customer_id: str
    product: str
    issue_type: str
    description: str
    sentiment: str = "neutral"
    language: str = "en"
    channel: str = "email"
    priority: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None

    model_config = ConfigDict(extra="allow")

    @field_validator("product", "issue_type")
    @classmethod
    def _clean_text(cls, value: str) -> str:
        return value.strip()


class TriageDecision(BaseModel):
    ticket_id: str
    urgency: Urgency
    product: str
    issue_type: str
    sentiment: str
    language: str
    intents: list[str]
    action: Action
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    customer_history_summary: str = ""
    kb_summary: str = ""
    safety_checks: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

#STRICT SCHEMA FOR TRIAGE DECISION VALIDATION, USED BY GUARDRAILS AND FALLBACK LOGIC
TRIAGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "ticket_id": {"type": "string"},
        "urgency": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
        "product": {"type": "string", "minLength": 1},
        "issue_type": {"type": "string", "minLength": 1},
        "sentiment": {"type": "string", "minLength": 1},
        "language": {"type": "string", "minLength": 1},
        "intents": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "action": {"type": "string", "enum": ["auto_respond", "route_to_specialist", "escalate_to_human"]},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "reasoning": {"type": "string", "minLength": 10},
        "customer_history_summary": {"type": "string"},
        "kb_summary": {"type": "string"},
        "safety_checks": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "ticket_id",
        "urgency",
        "product",
        "issue_type",
        "sentiment",
        "language",
        "intents",
        "action",
        "confidence",
        "reasoning",
        "customer_history_summary",
        "kb_summary",
        "safety_checks",
    ],
    "additionalProperties": False,
}
