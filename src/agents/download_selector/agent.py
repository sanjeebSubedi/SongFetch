from __future__ import annotations

import json
from typing import Literal

from src.agents._shared import build_structured_output_prompt
from src.agents.download_selector.prompt import DOWNLOAD_SELECTOR_INSTRUCTIONS
from src.agents.download_selector.schema import DownloadAudioSelection
from src.agents.metadata_selector.schema import MetadataSelection
from src.providers.ollama import (
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_TEMPERATURE,
    OllamaConfig,
    generate_structured_response,
)
from src.types import SearchResult


def select_download_audio_request(
    user_input: str,
    metadata_selection: MetadataSelection,
    search_results: list[SearchResult],
    *,
    requested_format: Literal["mp3", "m4a"],
    model: str = DEFAULT_OLLAMA_MODEL,
    host: str = DEFAULT_OLLAMA_HOST,
    temperature: float = DEFAULT_OLLAMA_TEMPERATURE,
) -> DownloadAudioSelection:
    if not search_results:
        raise ValueError("search_results must not be empty")

    config = OllamaConfig(
        model=model,
        host=host,
        temperature=temperature,
    )
    return generate_structured_response(
        user_input=_build_user_prompt(
            user_input,
            metadata_selection,
            search_results,
            requested_format=requested_format,
        ),
        response_model=DownloadAudioSelection,
        system_prompt=_build_system_prompt(),
        config=config,
    )


def _build_system_prompt() -> str:
    return build_structured_output_prompt(
        DOWNLOAD_SELECTOR_INSTRUCTIONS,
        DownloadAudioSelection,
    )


def _build_user_prompt(
    user_input: str,
    metadata_selection: MetadataSelection,
    search_results: list[SearchResult],
    *,
    requested_format: Literal["mp3", "m4a"],
) -> str:
    reference_metadata = metadata_selection.model_dump()
    reference_duration_ms = metadata_selection.duration_ms
    # Normalize to the same unit as YouTube candidates for consistent comparisons.
    reference_metadata["duration_seconds"] = round(reference_duration_ms / 1000)
    reference_metadata.pop("duration_ms", None)

    payload = {
        "original_user_request": user_input.strip(),
        "requested_format": requested_format,
        "reference_metadata": reference_metadata,
        "youtube_candidates": [
            {
                "rank": index,
                "id": result.get("id"),
                "title": result.get("title"),
                "uploader": result.get("uploader"),
                "duration_seconds": result.get("duration_seconds"),
                "view_count": result.get("view_count"),
                "webpage_url": result.get("webpage_url"),
            }
            for index, result in enumerate(search_results, start=1)
        ],
    }
    return json.dumps(payload, indent=2)
