import json


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
