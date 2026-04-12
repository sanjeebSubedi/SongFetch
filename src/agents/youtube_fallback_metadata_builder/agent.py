from __future__ import annotations

import json

from src.agents._shared import build_structured_output_prompt
from src.agents.youtube_fallback_metadata_builder.prompt import (
    YOUTUBE_FALLBACK_METADATA_INSTRUCTIONS,
)
from src.agents.youtube_fallback_metadata_builder.schema import (
    YouTubeFallbackMetadata,
)
from src.providers.ollama import (
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_TEMPERATURE,
    OllamaConfig,
    generate_structured_response,
)
from src.types import SearchResult


def build_youtube_fallback_metadata(
    user_input: str,
    selected_result: SearchResult | None,
    *,
    model: str = DEFAULT_OLLAMA_MODEL,
    host: str = DEFAULT_OLLAMA_HOST,
    temperature: float = DEFAULT_OLLAMA_TEMPERATURE,
) -> YouTubeFallbackMetadata:
    config = OllamaConfig(
        model=model,
        host=host,
        temperature=temperature,
    )
    return generate_structured_response(
        user_input=_build_user_prompt(user_input, selected_result),
        response_model=YouTubeFallbackMetadata,
        system_prompt=_build_system_prompt(),
        config=config,
    )


def _build_system_prompt() -> str:
    return build_structured_output_prompt(
        YOUTUBE_FALLBACK_METADATA_INSTRUCTIONS,
        YouTubeFallbackMetadata,
    )


def _build_user_prompt(user_input: str, selected_result: SearchResult | None) -> str:
    payload = {
        "original_user_request": user_input.strip(),
        "youtube_title": selected_result.get("title") if selected_result else None,
        "youtube_description": selected_result.get("description")
        if selected_result
        else None,
        "duration_seconds": selected_result.get("duration_seconds")
        if selected_result
        else None,
        "youtube_thumbnail_url": _build_thumbnail_url(selected_result),
    }
    return json.dumps(payload, indent=2)


def _build_thumbnail_url(selected_result: SearchResult | None) -> str | None:
    if not selected_result:
        return None

    video_id = _extract_video_id(selected_result)
    if not video_id:
        return None
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


def _extract_video_id(selected_result: SearchResult) -> str | None:
    video_id = selected_result.get("id")
    if isinstance(video_id, str) and video_id.strip():
        return video_id.strip()

    webpage_url = selected_result.get("webpage_url")
    if not isinstance(webpage_url, str) or not webpage_url.strip():
        return None

    stripped = webpage_url.strip()
    for marker in ("watch?v=", "youtu.be/"):
        if marker not in stripped:
            continue
        candidate = stripped.split(marker, maxsplit=1)[1]
        candidate = candidate.split("&", maxsplit=1)[0]
        candidate = candidate.split("?", maxsplit=1)[0]
        candidate = candidate.split("/", maxsplit=1)[0]
        if candidate:
            return candidate
    return None
