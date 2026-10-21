from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from app.models.triage import SupportTicket, TriageDecision

__all__ = ["SupportTicket", "TriageDecision", "normalize_ticket"]


def normalize_ticket(payload: Mapping[str, Any] | str) -> SupportTicket:
    if isinstance(payload, str):
        payload = json.loads(payload)
    return SupportTicket.model_validate(payload)
