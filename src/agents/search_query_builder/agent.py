from __future__ import annotations

from src.agents._shared import build_structured_output_prompt
from src.agents.search_query_builder.prompt import SEARCH_QUERY_BUILDER_INSTRUCTIONS
from src.agents.search_query_builder.schema import SongRequest
from src.providers.ollama import (
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_TEMPERATURE,
    OllamaConfig,
    generate_structured_response,
)


def build_song_request(
    user_input: str,
    *,
    model: str = DEFAULT_OLLAMA_MODEL,
    host: str = DEFAULT_OLLAMA_HOST,
    temperature: float = DEFAULT_OLLAMA_TEMPERATURE,
) -> SongRequest:
    config = OllamaConfig(
        model=model,
        host=host,
        temperature=temperature,
    )
    return generate_structured_response(
        user_input=user_input,
        response_model=SongRequest,
        system_prompt=_build_system_prompt(),
        config=config,
    )


def parse_download_request(
    user_input: str,
    *,
    model: str = DEFAULT_OLLAMA_MODEL,
    host: str = DEFAULT_OLLAMA_HOST,
    temperature: float = DEFAULT_OLLAMA_TEMPERATURE,
) -> SongRequest:
    """Backward-compatible alias while the workflow is still evolving."""
    return build_song_request(
        user_input,
        model=model,
        host=host,
        temperature=temperature,
    )


def _build_system_prompt() -> str:
    return build_structured_output_prompt(
        SEARCH_QUERY_BUILDER_INSTRUCTIONS,
        SongRequest,
    )
