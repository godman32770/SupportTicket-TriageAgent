from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TelemetryEvent:
    event: str
    ticket_id: str | None = None
    action: str | None = None
    urgency: str | None = None
    latency_ms: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TelemetryRecorder:
    events: list[TelemetryEvent] = field(default_factory=list)

    def record(self, event: TelemetryEvent) -> None:
        self.events.append(event)

    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for event in self.events:
            counts[event.event] = counts.get(event.event, 0) + 1
        return counts

    def last_event(self) -> TelemetryEvent | None:
        if not self.events:
            return None
        return self.events[-1]
