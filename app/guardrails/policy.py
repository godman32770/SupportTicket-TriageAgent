from __future__ import annotations

from typing import Any, Mapping


class PolicyGuardrail:
    VALID_URGENCY = {"low", "medium", "high", "critical"}
    VALID_ACTIONS = {"auto_respond", "route_to_specialist", "escalate_to_human"}

    # Tunable thresholds
    MIN_CONFIDENCE_FOR_AUTO = 0.75

    def _contains_any(self, text: str, keywords: list[str]) -> bool:
        t = (text or "").lower()
        return any(k.lower() in t for k in keywords)

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

        # Basic structural checks
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

        # Existing safety rules
        if urgency == "critical" and action == "auto_respond":
            issues.append("critical tickets cannot be auto-responded.")
        if urgency in {"high", "critical"} and action == "auto_respond":
            issues.append("high-risk tickets require specialist or human escalation.")
        if urgency == "low" and action == "escalate_to_human":
            issues.append("low urgency tickets should not be escalated to human.")

        # New guardrails
        # 1) billing_no_auto: billing disputes, chargebacks or multiple unresolved payments must not be auto-responded
        if action == "auto_respond" and (
            self._contains_any(issue_type, ["billing", "chargeback", "dispute"]) or
            self._contains_any(history, ["chargeback", "dispute", "unresolved payment", "unresolved payments", "unresolved"]) 
        ):
            issues.append("billing dispute or unresolved payments must not be auto-responded (billing_no_auto)")

        # 2) enterprise_outage_escalate: enterprise customers experiencing outage should escalate to human and be critical
        if self._contains_any(product, ["enterprise"]) and self._contains_any(issue_type + " " + reasoning, ["outage", "down", "service unavailable"]):
            if action != "escalate_to_human" or urgency != "critical":
                issues.append("enterprise outage must be escalated and marked critical (enterprise_outage_escalate)")

        # 3) sec_escalate / legal_threat_escalate
        if self._contains_any(issue_type + " " + reasoning + " " + " ".join(intents), ["security", "breach", "data loss", "legal", "lawsuit", "threat"]):
            if action == "auto_respond":
                issues.append("security or legal threats must not be auto-responded (sec_escalate / legal_threat_escalate)")
            if urgency in {"low", "medium"}:
                issues.append("security/legal issues must be at least high urgency")

        # 4) prompt_injection_escalate: detect suspicious instruction-bypass text in reasoning or safety_checks
        if self._contains_any(reasoning, ["ignore previous", "bypass", "prompt injection", "malicious", "ignore instructions"]) or any("prompt_injection" in str(s).lower() for s in safety_checks):
            issues.append("prompt injection suspected; escalate and discard draft (prompt_injection_escalate)")

        # 5) no_promises: replies that promise refunds/ETA/compensation must not be auto-replied; hold instead
        if action == "auto_respond" and self._contains_any(reasoning, ["refund", "compensation", "eta", "estimated time", "we will refund", "we will compensate"]):
            issues.append("draft contains promise of refund/ETA/compensation; hold reply for human review (no_promises)")

        # 6) draft_language_matches: ensure declared language is present; placeholder check for mismatches flagged in safety_checks
        if any(str(s).lower() == "language_mismatch" for s in safety_checks):
            issues.append("draft language does not match ticket language (draft_language_matches)")

        # 7) unverified_citations / ungrounded_auto_respond: auto replies must have KB context
        if action == "auto_respond" and (not kb or self._contains_any(kb, ["no matching kb", "no matching kb entries", "no matching entries"])):
            issues.append("auto_respond requires grounded KB evidence; route to specialist if KB missing (ungrounded_auto_respond)")

        # 8) low_confidence_escalate / action_matches_intents: low confidence should prevent auto-reply
        if confidence < self.MIN_CONFIDENCE_FOR_AUTO and action == "auto_respond":
            issues.append("confidence below threshold for safe auto-respond; escalate or route (low_confidence_escalate)")

        # 9) action must align with intents (simple heuristic: if intent contains 'escalate' require escalate)
        if isinstance(intents, list) and any(self._contains_any(i, ["escalat", "human", "specialist"]) for i in intents) and action == "auto_respond":
            issues.append("identified intents require human or specialist routing; auto_respond is not appropriate (action_matches_intents)")

        return issues


__all__ = ["PolicyGuardrail"]
