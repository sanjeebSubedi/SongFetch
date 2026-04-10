from __future__ import annotations

import json

from src.agents._shared import build_structured_output_prompt
from src.agents.metadata_selector.prompt import METADATA_SELECTOR_INSTRUCTIONS
from src.agents.metadata_selector.schema import MetadataSelection
from src.providers.ollama import (
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_TEMPERATURE,
    OllamaConfig,
    generate_structured_response,
)
from src.types import MusicMetadataResult


def select_metadata_match(
    user_input: str,
    metadata_matches: list[MusicMetadataResult],
    *,
    model: str = DEFAULT_OLLAMA_MODEL,
    host: str = DEFAULT_OLLAMA_HOST,
    temperature: float = DEFAULT_OLLAMA_TEMPERATURE,
) -> MetadataSelection:
    if not metadata_matches:
        raise ValueError("metadata_matches must not be empty")

    candidates_with_track_identity = [
        match
        for match in metadata_matches
        if match.get("track_id") and match.get("collection_id")
    ]
    if not candidates_with_track_identity:
        raise ValueError(
            "metadata_matches must include at least one candidate with track_id and collection_id"
        )

    config = OllamaConfig(
        model=model,
        host=host,
        temperature=temperature,
    )
    return generate_structured_response(
        user_input=_build_user_prompt(user_input, candidates_with_track_identity),
        response_model=MetadataSelection,
        system_prompt=_build_system_prompt(),
        config=config,
    )


def _build_system_prompt() -> str:
    return build_structured_output_prompt(
        METADATA_SELECTOR_INSTRUCTIONS,
        MetadataSelection,
    )


def _build_user_prompt(
    user_input: str,
    metadata_matches: list[MusicMetadataResult],
) -> str:
    payload = {
        "original_user_request": user_input.strip(),
        "itunes_candidates": [
            {
                "rank": index,
                "track_id": match.get("track_id"),
                "collection_id": match.get("collection_id"),
                "title": match.get("title"),
                "artist": match.get("artist"),
                "album": match.get("album"),
                "release_date": match.get("release_date"),
                "duration_ms": match.get("duration_ms"),
                "track_explicitness": match.get("track_explicitness"),
                "is_explicit": match.get("is_explicit"),
                "track_number": match.get("track_number"),
                "disc_number": match.get("disc_number"),
                "primary_genre_name": match.get("primary_genre_name"),
                "artwork_url": match.get("artwork_url"),
                "preview_url": match.get("preview_url"),
                "track_view_url": match.get("track_view_url"),
                "collection_view_url": match.get("collection_view_url"),
            }
            for index, match in enumerate(metadata_matches, start=1)
        ],
    }
    return json.dumps(payload, indent=2)
