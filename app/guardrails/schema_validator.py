from __future__ import annotations

import jsonschema
from jsonschema import ValidationError

from app.models.triage import TRIAGE_SCHEMA


class SchemaValidator:
    def validate(self, payload: object) -> list[str]:
        try:
            jsonschema.validate(instance=payload, schema=TRIAGE_SCHEMA)
            return []
        except ValidationError as exc:
            return [f"schema error: {exc.message}"]


__all__ = ["SchemaValidator", "TRIAGE_SCHEMA"]
