from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_TH_PHONE_RE = re.compile(r"\b(?:\+?66|0)\d{9,10}\b")
_US_PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b")
_NATIONAL_ID_RE = re.compile(r"\b\d{13}\b")
_CREDIT_CARD_RE = re.compile(r"\b(?:\d{4}[- ]?){3}\d{4}\b")
_PII_PATTERNS = [
    ("EMAIL", _EMAIL_RE),
    ("TH_PHONE", _TH_PHONE_RE),
    ("PHONE", _US_PHONE_RE),
    ("NATIONAL_ID", _NATIONAL_ID_RE),
    ("CARD", _CREDIT_CARD_RE),
]


@dataclass(frozen=True)
class RedactionResult:
    text: str
    mapping: dict[str, str]


def redact_with_mapping(text: str) -> RedactionResult:
    """Replace PII before an LLM call and retain the mapping locally only."""
    mapping: dict[str, str] = {}
    redacted = text
    counters: dict[str, int] = {}
    for label, pattern in _PII_PATTERNS:
        def replace(match: re.Match[str], pii_label: str = label) -> str:
            counters[pii_label] = counters.get(pii_label, 0) + 1
            token = f"<{pii_label}_{counters[pii_label]}>"
            mapping[token] = match.group(0)
            return token

        redacted = pattern.sub(replace, redacted)
    return RedactionResult(redacted, mapping)


def sanitize_untrusted_text(text: str) -> str:
    """Prevent customer text from closing the untrusted-data boundary."""
    return re.sub(r"</?untrusted_[^>]*>", "[removed-boundary-marker]", text, flags=re.IGNORECASE)


def sanitize_ticket_for_llm(ticket: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Send only fields needed for triage; return the PII map to the caller."""
    fields = ("ticket_id", "customer_id", "product", "issue_type", "description", "sentiment", "language")
    result: dict[str, Any] = {key: ticket.get(key) for key in fields if key in ticket}
    result["description"] = sanitize_untrusted_text(str(result.get("description", "")))
    redacted = redact_with_mapping(result["description"])
    result["description"] = redacted.text
    metadata = ticket.get("metadata")
    if isinstance(metadata, dict):
        allowed = {key: metadata[key] for key in ("subscription_plan", "open_ticket_count") if key in metadata}
        if allowed:
            result["metadata"] = allowed
    return result, redacted.mapping


def redact_pii(text: str) -> str:
    redacted = text
    for label, pattern in _PII_PATTERNS:
        redacted = pattern.sub(f"[{label}]", redacted)
    return redacted


__all__ = ["RedactionResult", "redact_pii", "redact_with_mapping", "sanitize_ticket_for_llm", "sanitize_untrusted_text"]
