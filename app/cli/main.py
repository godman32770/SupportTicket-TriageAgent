from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from app.agent.triage_agent import TriageAgent


def _load_dotenv() -> None:
    """Load simple KEY=value entries without adding a runtime dependency."""
    path = Path.cwd() / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() and key.strip() not in os.environ:
            os.environ[key.strip()] = value.strip().strip('"').strip("'")


def _load_ticket_payload(args: argparse.Namespace) -> str | dict[str, Any] | list[dict[str, Any]]:
    if args.ticket is not None:
        payload: str | Any = args.ticket
        try:
            parsed: str | dict[str, Any] | list[dict[str, Any]] = json.loads(payload)
        except json.JSONDecodeError:
            return payload
        return parsed
    if args.ticket_file is not None:
        path = Path(args.ticket_file)
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            raise FileNotFoundError(f"Ticket file not found: {path}")
        with path.open("r", encoding="utf-8-sig") as fh:
            loaded_payload: str | dict[str, Any] | list[dict[str, Any]] = json.load(fh)
        return loaded_payload
    raise ValueError("Either --ticket or --ticket-file is required.")


#CLI ENTRY POINT FOR TRIAGE DECISION GENERATION, WITH ARGUMENT PARSING AND ERROR HANDLING
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Support triage CLI")
    parser.add_argument("--ticket", help="Ticket JSON as a string")
    parser.add_argument("--ticket-file", help="Path to a JSON file containing the ticket")
    parser.add_argument("--mode", choices=["offline", "live"], default="offline")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    parser.add_argument("--model", default="gpt-4o-mini", help="Live model name")
    parser.add_argument("--metrics", action="store_true", help="Include latency and token metrics in the output")
    args = parser.parse_args(argv)

    try:
        payload = _load_ticket_payload(args)
        if args.mode == "live":
            _load_dotenv()
        agent = TriageAgent(mode=args.mode, model=args.model)
        output: object

        if isinstance(payload, list):
            decisions = [agent.run(ticket) for ticket in payload]
            output = [decision.model_dump(mode="json") for decision in decisions]
        else:
            decision = agent.run(payload)
            output = decision.model_dump(mode="json")

        if args.metrics:
            output = {"results": output, "metrics": agent.last_run_metrics}
        print(json.dumps(output, indent=2 if args.pretty else None))
        return 0
    except (FileNotFoundError, ValueError, TypeError, OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
