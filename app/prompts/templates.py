from __future__ import annotations

import json
from typing import Any, Mapping

TriagePromptTemplate = """You are a safe AI customer support triage assistant.

Task:
- classify urgency as low, medium, high, or critical
- extract fields: product, issue_type, sentiment, language, intents
- decide among: auto_respond, route_to_specialist, escalate_to_human
- reason safely using customer history and knowledge base references
- use only a JSON object that matches the required schema

Ticket:
{ticket}

Customer history:
{customer_history}

Knowledge base:
{kb}

Return JSON only.
"""


def build_prompt(ticket: Mapping[str, Any], context: Mapping[str, Any]) -> str:
    return TriagePromptTemplate.format(
        ticket=json.dumps(ticket, ensure_ascii=False, default=str),
        customer_history=context.get("customer_history", ""),
        kb=context.get("kb", ""),
    )

