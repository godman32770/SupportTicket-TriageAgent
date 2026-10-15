from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from app.agent.triage_agent import TriageAgent


def _load_ticket_payload(args: argparse.Namespace) -> str | dict[str, Any]:
    if args.ticket is not None:
        return args.ticket
    if args.ticket_file is not None:
        path = Path(args.ticket_file)
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            raise FileNotFoundError(f"Ticket file not found: {path}")
        with path.open("r", encoding="utf-8-sig") as fh:
            return json.load(fh)
    raise ValueError("Either --ticket or --ticket-file is required.")

#CLI ENTRY POINT FOR TRIAGE DECISION GENERATION, WITH ARGUMENT PARSING AND ERROR HANDLING
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Support triage CLI")
    parser.add_argument("--ticket", help="Ticket JSON as a string")
    parser.add_argument("--ticket-file", help="Path to a JSON file containing the ticket")
    parser.add_argument("--mode", choices=["offline", "live"], default="offline")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    parser.add_argument("--model", default="gpt-4o-mini", help="Live model name")
    args = parser.parse_args(argv)

    try:
        payload = _load_ticket_payload(args)
        agent = TriageAgent(mode=args.mode, model=args.model)
        decision = agent.run(payload)
        output = decision.model_dump(mode="json")
        print(json.dumps(output, indent=2 if args.pretty else None))
        return 0
    except Exception as exc:  # pragma: no cover - CLI error path
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
