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

    candidates_with_release_group = [
        match for match in metadata_matches if match.get("release_group_id")
    ]
    if not candidates_with_release_group:
        raise ValueError(
            "metadata_matches must include at least one candidate with release_group_id"
        )

    config = OllamaConfig(
        model=model,
        host=host,
        temperature=temperature,
    )
    return generate_structured_response(
        user_input=_build_user_prompt(user_input, candidates_with_release_group),
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
        "musicbrainz_candidates": [
            {
                "rank": index,
                "recording_id": match.get("recording_id"),
                "release_group_id": match.get("release_group_id"),
                "title": match.get("title"),
                "artist": match.get("artist"),
                "artist_credit": match.get("artist_credit"),
                "album": match.get("album"),
                "first_release_date": match.get("first_release_date"),
                "length_ms": match.get("length_ms"),
                "disambiguation": match.get("disambiguation"),
                "score": match.get("score"),
                "release_group_primary_type": match.get("release_group_primary_type"),
                "release_group_secondary_types": match.get(
                    "release_group_secondary_types"
                ),
                "release_status": match.get("release_status"),
                "musicbrainz_url": match.get("musicbrainz_url"),
            }
            for index, match in enumerate(metadata_matches, start=1)
        ],
    }
    return json.dumps(payload, indent=2)
