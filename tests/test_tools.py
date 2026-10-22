import json

from app.tools import KBLookupTool


def test_eval_fixture_is_valid_json():
    fixture = json.loads(
        """
        {
          "predictions": [
            {"urgency": "low", "action": "auto_respond"},
            {"urgency": "high", "action": "route_to_specialist"},
            {"urgency": "critical", "action": "escalate_to_human"}
          ],
          "gold": [
            {"urgency": "low", "action": "auto_respond"},
            {"urgency": "medium", "action": "route_to_specialist"},
            {"urgency": "critical", "action": "escalate_to_human"}
          ]
        }
        """
    )

    assert len(fixture["predictions"]) == 3
    assert len(fixture["gold"]) == 3


def test_kb_lookup_uses_description_when_structured_fields_are_unhelpful():
    result = KBLookupTool().lookup(
        "web",
        "unknown",
        "I cannot log in because the password reset email never arrives.",
    )

    assert result.success is True
    assert "Password reset" in result.summary
