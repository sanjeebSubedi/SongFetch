from __future__ import annotations

import json

from src.agents._shared import build_structured_output_prompt
from src.agents.metadata_request_builder.prompt import (
    METADATA_REQUEST_BUILDER_INSTRUCTIONS,
)
from src.agents.metadata_request_builder.schema import MetadataLookupRequest
from src.providers.ollama import (
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_TEMPERATURE,
    OllamaConfig,
    generate_structured_response,
)
from src.types import SearchResult


def build_metadata_lookup_request(
    user_input: str,
    search_results: list[SearchResult],
    *,
    model: str = DEFAULT_OLLAMA_MODEL,
    host: str = DEFAULT_OLLAMA_HOST,
    temperature: float = DEFAULT_OLLAMA_TEMPERATURE,
) -> MetadataLookupRequest:
    if not search_results:
        raise ValueError("search_results must not be empty")

    config = OllamaConfig(
        model=model,
        host=host,
        temperature=temperature,
    )
    return generate_structured_response(
        user_input=_build_user_prompt(user_input, search_results),
        response_model=MetadataLookupRequest,
        system_prompt=_build_system_prompt(),
        config=config,
    )


def _build_system_prompt() -> str:
    return build_structured_output_prompt(
        METADATA_REQUEST_BUILDER_INSTRUCTIONS,
        MetadataLookupRequest,
    )


def _build_user_prompt(user_input: str, search_results: list[SearchResult]) -> str:
    payload = {
        "original_user_request": user_input.strip(),
        "youtube_search_results": [
            {
                "rank": index,
                "title": result.get("title"),
                "uploader": result.get("uploader"),
                "view_count": result.get("view_count"),
                "duration_seconds": result.get("duration_seconds"),
                "webpage_url": result.get("webpage_url"),
            }
            for index, result in enumerate(search_results[:5], start=1)
        ],
    }
    return json.dumps(payload, indent=2)
