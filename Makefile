.PHONY: test lint typecheck check demo-live eval eval-benchmark eval-assignment

test:
	python -m pytest -q

lint:
	python -m ruff check app eval tests

typecheck:
	python -m mypy app

check: lint typecheck test

demo-live:
	python -m app.cli.main --ticket-file tickets/sample_ticket.json --mode live --model $${MODEL_NAME:-gpt-4o-mini} --metrics --pretty

eval:
	python -m eval.run_eval --file eval/sample_eval.json --mode offline --fail-on-critical

eval-benchmark:
	python -m eval.run_eval --file eval/benchmark_30.json --mode offline --fail-on-critical

eval-assignment:
	python -m eval.run_eval --file eval/assignment_origin_eval.json --mode offline --fail-on-critical
