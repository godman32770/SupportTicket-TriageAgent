from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.eval.metrics import evaluate_triage

#COMPARE TRIAGE PREDICTIONS TO GOLD STANDARD AND OUTPUT EVALUATION RESULTS, WITH SAFE FALLBACKS
def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate triage model quality.")
    parser.add_argument("--file", type=str, default="eval/sample_eval.json")
    args = parser.parse_args(argv)

    payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
    result = evaluate_triage(payload["predictions"], payload["gold"])
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

