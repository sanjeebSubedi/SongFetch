from __future__ import annotations

import json

from pydantic import BaseModel


def build_structured_output_prompt(
    instructions: str,
    response_model: type[BaseModel],
) -> str:
    schema_json = json.dumps(response_model.model_json_schema(), indent=2)
    return f"{instructions}\n\nJSON schema:\n{schema_json}"
