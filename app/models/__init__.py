from __future__ import annotations

from typing import Any, Mapping

from app.models.triage import SupportTicket, TriageDecision


def normalize_ticket(payload: Mapping[str, Any] | str) -> SupportTicket:
    if isinstance(payload, str):
        import json

        payload = json.loads(payload)
    return SupportTicket.model_validate(payload)
