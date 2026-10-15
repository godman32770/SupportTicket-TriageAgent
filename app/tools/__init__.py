from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ToolResult:
    success: bool
    summary: str
    payload: dict[str, Any] | None = None
    error: str | None = None


class CustomerHistoryTool:
    def __init__(self, dataset: dict[str, list[str]] | None = None):
        self.dataset = dataset or {
            "C-100": [
                "Previous order issue resolved after replacement shipment.",
                "Customer is generally positive but became frustrated after a billing delay.",
            ],
            "C-200": [
                "Past ticket on account security reset; customer requested quick turnaround.",
            ],
        }

    def fetch(self, customer_id: str) -> ToolResult:
        history = self.dataset.get(customer_id, [])
        if not history:
            return ToolResult(success=True, summary=f"No prior customer history found for {customer_id}.")
        return ToolResult(success=True, summary=f"Customer {customer_id} previously reported: {'; '.join(history)}")

#LOOKUP TOOL PROVIDES RELEVANT KNOWLEDGE BASE ENTRIES BASED ON PRODUCT AND ISSUE TYPE, WITH FALLBACKS
class KBLookupTool:
    def __init__(self, knowledge_base: dict[str, list[str]] | None = None):
        self.knowledge_base = knowledge_base or {
            "payment": ["Billing issues often require verification of recent charges and account status."],
            "login": ["Password reset flows are available; if MFA issues persist, escalate to specialist."],
            "mobile_app": ["Clear app cache and reinstall if the app crashes after update."],
            "account": ["Account lockouts can be solved by verification and a guided reset workflow."],
        }

    def lookup(self, product: str, issue_type: str) -> ToolResult:
        search_key = issue_type.lower()
        matches = self.knowledge_base.get(search_key, [])
        if not matches and product:
            matches = self.knowledge_base.get(product.lower(), [])
        if not matches:
            return ToolResult(success=True, summary="No matching KB entries found; use general support workflow.")
        return ToolResult(success=True, summary="; ".join(matches))


__all__ = ["CustomerHistoryTool", "KBLookupTool", "ToolResult"]
