from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.request import Request, urlopen


@dataclass
class ToolResult:
    success: bool
    summary: str
    payload: dict[str, Any] | None = None
    error: str | None = None


class CustomerHistoryTool:
    def __init__(self, dataset: dict[str, list[str]] | None = None, fail_on_fetch: bool = False):
        self.dataset = dataset or {
            "C-100": [
                "Previous order issue resolved after replacement shipment.",
                "Customer is generally positive but became frustrated after a billing delay.",
            ],
            "C-200": [
                "Past ticket on account security reset; customer requested quick turnaround.",
            ],
        }
        self.fail_on_fetch = fail_on_fetch

    def fetch(self, customer_id: str) -> ToolResult:
        try:
            if self.fail_on_fetch:
                raise RuntimeError("customer history tool unavailable")
            history = self.dataset.get(customer_id, [])
            if not history:
                return ToolResult(success=True, summary=f"No prior customer history found for {customer_id}.")
            return ToolResult(success=True, summary=f"Customer {customer_id} previously reported: {'; '.join(history)}")
        except (RuntimeError, ValueError, TypeError, OSError) as exc:  # pragma: no cover - defensive failure handling
            return ToolResult(success=False, summary="", error=str(exc))


class ServiceStatusTool:
    """Check a configurable status endpoint without network calls by default."""

    def __init__(self, status_url: str | None = None, timeout_seconds: float = 3.0):
        self.status_url = status_url or os.getenv("SERVICE_STATUS_URL")
        self.timeout_seconds = timeout_seconds

    def check(self, product: str, description: str = "", region: str = "") -> ToolResult:
        try:
            if not self.status_url:
                return ToolResult(
                    success=True,
                    summary="Status source is not configured; no platform-wide incident is confirmed.",
                    payload={"status": "unknown", "source": "unconfigured"},
                )
            request = Request(self.status_url, headers={"Accept": "application/json"})
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise TypeError("status endpoint must return a JSON object")
            status = payload.get("status") or payload.get("indicator") or payload.get("state") or "unknown"
            return ToolResult(
                success=True,
                summary=f"Configured service status for {product or 'the platform'}: {status}.",
                payload={"status": str(status), "region": region, "source": self.status_url},
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return ToolResult(success=False, summary="", error=f"service status lookup failed: {exc}")


#LOOKUP TOOL PROVIDES RELEVANT KNOWLEDGE BASE ENTRIES BASED ON PRODUCT AND ISSUE TYPE, WITH FALLBACKS
class KBLookupTool:
    def __init__(self, knowledge_base: dict[str, list[str]] | None = None, fail_on_lookup: bool = False):
        self.knowledge_base = knowledge_base or {
            "payment": ["Billing issues often require verification of recent charges and account status."],
            "billing": ["Billing issues often require verification of recent charges, duplicate payments, and account status."],
            "duplicate_charges": ["Duplicate charges require payment verification and specialist review before any refund is promised."],
            "login": ["Password reset flows are available; if MFA issues persist, escalate to specialist."],
            "mobile_app": ["Clear app cache and reinstall if the app crashes after update."],
            "account": ["Account lockouts can be solved by verification and a guided reset workflow."],
            "service_outage": ["For service outages, verify status and route affected enterprise customers to incident support."],
            "appearance_settings": ["Dark mode availability depends on the product release; route configuration issues and feature requests to a specialist."],
        }
        self.fail_on_lookup = fail_on_lookup

    def lookup(self, product: str, issue_type: str, description: str = "") -> ToolResult:
        try:
            if self.fail_on_lookup:
                raise RuntimeError("knowledge base lookup unavailable")
            search_key = issue_type.lower()
            matches = self.knowledge_base.get(search_key, [])
            if not matches and product:
                matches = self.knowledge_base.get(product.lower(), [])
            if not matches and description:
                text = description.lower()
                query_terms = {
                    "login": ("login", "log in", "password", "mfa", "locked out", "account access"),
                    "billing": ("billing", "invoice", "charge", "refund", "payment", "renewal"),
                    "bug": ("bug", "error", "crash", "broken", "500"),
                    "feature_request": ("feature", "support for", "add", "change the default"),
                    "general_help": ("how do i", "where can i", "help", "setup", "settings"),
                }
                for key, terms in query_terms.items():
                    if any(term in text for term in terms):
                        matches = self.knowledge_base.get(key, [])
                        if matches:
                            break
            if not matches:
                return ToolResult(success=True, summary="No matching KB entries found; use general support workflow.")
            return ToolResult(success=True, summary="; ".join(matches))
        except (RuntimeError, ValueError, TypeError, OSError) as exc:  # pragma: no cover - defensive failure handling
            return ToolResult(success=False, summary="", error=str(exc))


__all__ = ["CustomerHistoryTool", "KBLookupTool", "ServiceStatusTool", "ToolResult"]
