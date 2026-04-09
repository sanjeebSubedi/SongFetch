from __future__ import annotations

import json

from pydantic import BaseModel

SEARCH_QUERY_BUILDER_INSTRUCTIONS = """
You are a search query builder for a song download workflow.

Extract the song request into strict JSON that matches the provided schema.

Rules:
- Always return valid JSON only.
- Use the exact schema keys.
- song_name must contain only the song title.
- Set artist or album to null when unknown.
- Default format to "m4a" unless the user explicitly asks for "mp3".
- Build search_query as a concise, high-quality YouTube search string.
- Prefer song title and artist in search_query, and include album only if it meaningfully disambiguates.
""".strip()


def build_structured_output_prompt(
    instructions: str,
    response_model: type[BaseModel],
) -> str:
    schema_json = json.dumps(response_model.model_json_schema(), indent=2)
    return f"{instructions}\n\nJSON schema:\n{schema_json}"
