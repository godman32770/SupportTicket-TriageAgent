"""Regression tests for two keyword-matching gaps.

1. Account-access failures phrased as "cannot log in" (not only "cannot sign in")
   must be escalated to a human.
2. The safe fallback must match urgency keywords on word boundaries, so that
   "download" does not count as "down".
"""

from __future__ import annotations

import pytest

from app.agent.triage_agent import build_safe_fallback
from app.guardrails.policy import PolicyGuardrail
from app.models import normalize_ticket


def _decision(description: str, action: str) -> dict:
    return {
        "ticket_id": "T-TEST",
        "urgency": "medium",
        "product": "mobile_app",
        "issue_type": "login",
        "sentiment": "frustrated",
        "language": "en",
        "intents": ["login_help"],
        "action": action,
        "confidence": 0.95,
        "reasoning": "Routine login question.",
        "customer_history_summary": "No prior customer history found.",
        "kb_summary": "Password reset flows are available.",
        "safety_checks": [],
        "description": description,
    }


@pytest.mark.parametrize(
    "description",
    [
        "I cannot log in after password reset and it is urgent.",
        "I can't log in to my account.",
        "I am unable to log in since yesterday.",
        "I cannot login on the web app.",
        "Unable to sign in with my new phone.",
    ],
)
def test_login_failure_variants_require_human_escalation(description: str) -> None:
    issues = PolicyGuardrail().validate(_decision(description, "auto_respond"))
    assert any("account_access_escalate" in issue for issue in issues)

    issues = PolicyGuardrail().validate(_decision(description, "escalate_to_human"))
    assert not any("account_access_escalate" in issue for issue in issues)


def test_routine_password_reset_is_not_treated_as_access_failure() -> None:
    issues = PolicyGuardrail().validate(
        _decision("I need to reset my password for my family account.", "auto_respond")
    )
    assert not any("account_access_escalate" in issue for issue in issues)


def _ticket(description: str):
    return normalize_ticket(
        {
            "ticket_id": "T-TEST",
            "customer_id": "C-TEST",
            "product": "billing",
            "issue_type": "billing",
            "description": description,
            "language": "en",
            "sentiment": "neutral",
        }
    )


def test_fallback_does_not_mark_download_as_critical() -> None:
    fallback = build_safe_fallback(_ticket("Please help me download my invoice."), "", "")
    assert fallback["urgency"] == "high"
    assert fallback["action"] == "escalate_to_human"


@pytest.mark.parametrize(
    "description",
    ["The API is down for all users.", "We had a data loss after the update.", "There was an outage."],
)
def test_fallback_still_marks_real_critical_signals(description: str) -> None:
    fallback = build_safe_fallback(_ticket(description), "", "")
    assert fallback["urgency"] == "critical"
    assert fallback["action"] == "escalate_to_human"
