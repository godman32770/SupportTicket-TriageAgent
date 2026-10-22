"""Deterministic high-risk ticket-text signals shared by triage and policy checks."""

from __future__ import annotations


def detect_escalation_signals(text: str) -> set[str]:
    """Return high-risk signal names found in untrusted ticket text.

    The production API signal deliberately requires both production context and
    an API failure symptom, so ordinary API questions and integration bugs remain
    eligible for normal routing.
    """
    normalized = (text or "").lower().replace("-", " ").replace("_", " ")
    signals: set[str] = set()

    if any(
        phrase in normalized
        for phrase in (
            "privacy incident",
            "privacy breach",
            "privacy violation",
            "personal data",
            "personal information",
            "personally identifiable",
            "sensitive data",
            "private data",
            "pii",
            "data exposure",
            "data exposed",
            "data leak",
            "leaked data",
            "records exposed",
            "credit card details",
            "api keys",
            "stored customer credentials",
            "reveal your system prompt",
            "system override",
            "system override mode",
        )
    ):
        signals.add("privacy")

    if any(
        phrase in normalized
        for phrase in (
            "gdpr",
            "article 15",
            "article 17",
            "right to be forgotten",
            "data subject request",
            "erasure request",
            "erase all personal data",
            "delete all personal data",
        )
    ):
        signals.add("gdpr")

    if any(
        phrase in normalized
        for phrase in (
            "cross tenant",
            "another tenant",
            "other tenant",
            "another organization",
            "other customer",
            "tenant isolation",
            "tenant boundary",
            "shared tenant",
        )
    ) and any(phrase in normalized for phrase in ("data", "document", "record", "access", "view", "exposure")):
        signals.add("cross_tenant")

    production_context = any(phrase in normalized for phrase in ("production", "prod ", "live environment", "live system"))
    api_failure = any(
        phrase in normalized
        for phrase in (
            "api failure",
            "api error",
            "api is down",
            "api unavailable",
            "api timeout",
            "api timed out",
            "api 429",
            "http 429",
            "api 500",
            "http 500",
            "api 502",
            "http 502",
            "api 503",
            "http 503",
            "api 504",
            "http 504",
            "api 5xx",
            "api rate limit",
            "api rate limiting",
            "rate limiting error",
            "api failing",
            "api errors",
        )
    )
    if production_context and api_failure:
        signals.add("production_api_failure")

    if any(phrase in normalized for phrase in ("locked out", "cannot access", "unable to access", "cannot sign in", "can't sign in")) and any(
        phrase in normalized for phrase in ("entire organization", "all employees", "everyone on our team", "300 employees", "company-wide", "org-wide")
    ):
        signals.add("organization_wide_lockout")

    return signals


def detect_specialist_signals(text: str) -> set[str]:
    """Return contained issues that require specialist routing, not automation."""
    normalized = (text or "").lower().replace("-", " ").replace("_", " ")
    signals: set[str] = set()
    if any(phrase in normalized for phrase in ("integration", "webhook", "zapier", "salesforce", "stop syncing", "stopped syncing", "payloads are coming empty")):
        signals.add("integration_failure")
    if any(phrase in normalized for phrase in ("screen reader", "screen readers", "nvda", "jaws", "aria label", "accessibility")):
        signals.add("accessibility_defect")
    if any(phrase in normalized for phrase in ("saml sso", "single sign-on", "sso configured", "sso setup")):
        signals.add("sso_configuration")
    if any(phrase in normalized for phrase in ("audit logs", "retention controls", "compliance reporting")):
        signals.add("compliance_question")
    if any(phrase in normalized for phrase in ("takes over", "slow to load", "load", "time out", "timeout", "times out", "40 seconds")) and any(
        phrase in normalized for phrase in ("dashboard", "reports", "performance", "slow", "load")
    ):
        signals.add("performance_degradation")
    return signals


__all__ = ["detect_escalation_signals", "detect_specialist_signals"]
