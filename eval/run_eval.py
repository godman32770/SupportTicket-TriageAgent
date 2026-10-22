from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agent.triage_agent import TriageAgent
from app.eval.metrics import evaluate_triage


#COMPARE TRIAGE PREDICTIONS TO GOLD STANDARD AND OUTPUT EVALUATION RESULTS, WITH SAFE FALLBACKS
def _load_payload(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "tickets" in payload and "gold" in payload:
        return payload
    if isinstance(payload, dict) and "predictions" in payload and "gold" in payload:
        return payload
    raise ValueError("Eval file must contain either 'tickets' + 'gold' or 'predictions' + 'gold'.")


def _generate_predictions(payload: dict[str, Any], mode: str, model: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if "tickets" in payload:
        agent = TriageAgent(mode=mode, model=model)
        preds: list[dict[str, Any]] = []
        cases: list[dict[str, Any]] = []
        for ticket in payload["tickets"]:
            try:
                actual = agent.run(ticket).model_dump(mode="json")
                actual.update(agent.last_run_metrics)
                preds.append(actual)
                index = len(cases)
                cases.append({"ticket": ticket, "expected": payload["gold"][index], "actual": actual})
            except (RuntimeError, ValueError, TypeError, OSError) as exc:
                print(f"[eval] {ticket.get('ticket_id')} failed: {exc}")
                actual = {"error": str(exc)}
                preds.append(actual)
                index = len(cases)
                cases.append({"ticket": ticket, "expected": payload["gold"][index], "actual": actual})
        return preds, cases
    return payload["predictions"], []


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate triage model quality.")
    parser.add_argument("--file", type=str, default="eval/sample_eval.json")
    parser.add_argument("--mode", choices=["offline", "live"], default="offline")
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--results-dir", default="eval/results")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--fail-on-critical", action="store_true")
    args = parser.parse_args(argv)

    payload = _load_payload(args.file)
    predictions, cases = _generate_predictions(payload, mode=args.mode, model=args.model)
    gold = payload["gold"]
    result = evaluate_triage(predictions, gold)
    print(json.dumps(result, indent=2))
    if cases and not args.no_write:
        results_dir = Path(args.results_dir)
        results_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).date().isoformat()
        fixture_name = Path(args.file).stem
        output_path = results_dir / f"{fixture_name}-{args.mode}-{args.model.replace('/', '_')}-{stamp}.json"
        output_path.write_text(json.dumps({"model": args.model, "mode": args.mode, "metrics": result, "cases": cases}, indent=2), encoding="utf-8")
    if args.fail_on_critical and result.get("critical_cases_missed", 0) > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
