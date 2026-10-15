import json
import subprocess
import sys


def test_cli_with_json_ticket():
    ticket = json.dumps({
        "ticket_id": "T-CLI",
        "customer_id": "C-100",
        "product": "mobile_app",
        "issue_type": "login",
        "description": "I cannot log in and need help quickly.",
        "language": "en",
        "sentiment": "frustrated",
    })
    result = subprocess.run(
        [sys.executable, "-m", "app.cli.main", "--ticket", ticket, "--mode", "offline"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip())
    assert payload["ticket_id"] == "T-CLI"
    assert payload["urgency"] in {"low", "medium", "high", "critical"}
