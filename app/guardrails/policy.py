from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, ClassVar


class PolicyGuardrail:
    VALID_URGENCY: ClassVar[set[str]] = {"low", "medium", "high", "critical"}
    VALID_ACTIONS: ClassVar[set[str]] = {"auto_respond", "route_to_specialist", "escalate_to_human"}

    MIN_CONFIDENCE_FOR_AUTO = 0.75

    def _contains_any(self, text: str, keywords: list[str]) -> bool:
        t = re.sub(r"[_-]+", " ", (text or "").lower())
        normalized_keywords = [re.sub(r"[_-]+", " ", k.lower()) for k in keywords]
        return any(re.search(rf"\b{re.escape(k)}\b", t) for k in normalized_keywords)

    def _as_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, (list, tuple, set)):
            return " ".join(str(item) for item in value)
        return str(value)

    def _extract_ticket_text(self, decision: Mapping[str, Any] | object) -> str:
        if isinstance(decision, dict):
            message_fields = [
                decision.get("description"),
                decision.get("message"),
                decision.get("customer_message"),
                decision.get("customer_text"),
                decision.get("ticket_text"),
                decision.get("body"),
            ]
            metadata = decision.get("metadata")
            if isinstance(metadata, Mapping):
                message_fields.extend(
                    [
                        metadata.get("description"),
                        metadata.get("message"),
                        metadata.get("customer_message"),
                        metadata.get("ticket_text"),
                    ]
                )
            text = " ".join(self._as_text(val) for val in message_fields if val is not None)
            return text.strip()

        for attr in (
            "description",
            "message",
            "customer_message",
            "customer_text",
            "ticket_text",
            "body",
        ):
            value = getattr(decision, attr, None)
            if value is not None:
                return self._as_text(value)
        return self._as_text(getattr(decision, "reasoning", ""))

    def validate(self, decision: Mapping[str, Any] | object) -> list[str]:
        issues: list[str] = []

        if isinstance(decision, dict):
            urgency = str(decision.get("urgency", "")).lower()
            action = str(decision.get("action", "")).lower()
            product = str(decision.get("product", "")).strip()
            issue_type = str(decision.get("issue_type", "")).strip()
            intents = decision.get("intents", [])
            confidence = float(decision.get("confidence", -1.0))
            reasoning = str(decision.get("reasoning", ""))
            history = str(decision.get("customer_history_summary", ""))
            kb = str(decision.get("kb_summary", ""))
            safety_checks = decision.get("safety_checks", [])
        else:
            urgency = str(getattr(decision, "urgency", "")).lower()
            action = str(getattr(decision, "action", "")).lower()
            product = str(getattr(decision, "product", "")).strip()
            issue_type = str(getattr(decision, "issue_type", "")).strip()
            intents = getattr(decision, "intents", [])
            confidence = float(getattr(decision, "confidence", -1.0))
            reasoning = str(getattr(decision, "reasoning", ""))
            history = str(getattr(decision, "customer_history_summary", ""))
            kb = str(getattr(decision, "kb_summary", ""))
            safety_checks = getattr(decision, "safety_checks", [])

        ticket_text = self._extract_ticket_text(decision)
        signal_text = " ".join(
            filter(
                None,
                [
                    ticket_text,
                    product,
                    issue_type,
                    reasoning,
                    history,
                    kb,
                    self._as_text(intents),
                ],
            )
        )

        if urgency not in self.VALID_URGENCY:
            issues.append("urgency must be one of low, medium, high, critical.")
        if action not in self.VALID_ACTIONS:
            issues.append("action must be one of auto_respond, route_to_specialist, escalate_to_human.")
        if not product or not issue_type:
            issues.append("product and issue_type are required.")
        if not intents:
            issues.append("intents must contain at least one identified intent.")
        if not 0.0 <= confidence <= 1.0:
            issues.append("confidence must be between 0.0 and 1.0.")

        if urgency == "critical" and action == "auto_respond":
            issues.append("critical tickets cannot be auto-responded.")
        if urgency in {"high", "critical"} and action == "auto_respond":
            issues.append("high-risk tickets require specialist or human escalation.")

        if self._contains_any(
            signal_text,
            [
                "locked out",
                "cannot access",
                "unable to access",
                "mfa code is not working",
                "cannot sign in",
                "can't sign in",
            ],
        ) and action != "escalate_to_human":
            issues.append("account access failures require human escalation (account_access_escalate)")
        if action == "auto_respond" and (
            self._contains_any(issue_type, ["billing", "chargeback", "dispute"])
            or self._contains_any(history, ["chargeback", "dispute", "unresolved payment", "unresolved payments", "unresolved"])
            or self._contains_any(signal_text, ["chargeback", "billing dispute", "unresolved payment", "multiple unpaid invoices"])
        ):
            issues.append("billing dispute or unresolved payments must not be auto-responded (billing_no_auto)")

        if (
            self._contains_any(product, ["enterprise"])
            and self._contains_any(signal_text, ["outage", "down", "service unavailable", "system outage"])
            and (action != "escalate_to_human" or urgency != "critical")
        ):
            issues.append("enterprise outage must be escalated and marked critical (enterprise_outage_escalate)")

        if self._contains_any(signal_text, ["security", "breach", "data loss", "legal", "lawsuit", "threat"]):
            if action == "auto_respond":
                issues.append("security or legal threats must not be auto-responded (sec_escalate / legal_threat_escalate)")
            if urgency in {"low", "medium"} and action != "escalate_to_human":
                issues.append("security/legal issues must be at least high urgency")

        if (
            (self._contains_any(signal_text, ["ignore previous", "bypass", "prompt injection", "malicious", "ignore instructions"]) or any("prompt_injection" in str(s).lower() for s in safety_checks))
            and action == "auto_respond"
        ):
            issues.append("prompt injection suspected; escalate and discard draft (prompt_injection_escalate)")

        if action == "auto_respond" and self._contains_any(signal_text, ["refund", "compensation", "eta", "estimated time", "we will refund", "we will compensate"]):
            issues.append("draft contains promise of refund/ETA/compensation; hold reply for human review (no_promises)")

        if any(str(s).lower() == "language_mismatch" for s in safety_checks):
            issues.append("draft language does not match ticket language (draft_language_matches)")

        if action == "auto_respond" and (not kb or self._contains_any(kb, ["no matching kb", "no matching kb entries", "no matching entries"])):
            issues.append("auto_respond requires grounded KB evidence; route to specialist if KB missing (ungrounded_auto_respond)")

        if confidence < self.MIN_CONFIDENCE_FOR_AUTO and action == "auto_respond":
            issues.append("confidence below threshold for safe auto-respond; escalate or route (low_confidence_escalate)")

        if isinstance(intents, list) and any(self._contains_any(i, ["escalat", "human", "specialist"]) for i in intents) and action == "auto_respond":
            issues.append("identified intents require human or specialist routing; auto_respond is not appropriate (action_matches_intents)")

        return issues


__all__ = ["PolicyGuardrail"]
