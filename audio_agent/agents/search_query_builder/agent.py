from __future__ import annotations

import argparse
import sys

from audio_agent.agents.search_query_builder.prompt import (
    SEARCH_QUERY_BUILDER_INSTRUCTIONS,
    build_structured_output_prompt,
)
from audio_agent.agents.search_query_builder.schema import SongRequest
from audio_agent.providers.ollama import (
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a SongRequest JSON object from natural language with Ollama."
    )
    parser.add_argument(
        "user_input",
        nargs="+",
        help="Natural-language request to send to the search query builder agent",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_OLLAMA_MODEL,
        help="Ollama model name to use",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_OLLAMA_HOST,
        help="Host for the Ollama server",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=DEFAULT_OLLAMA_TEMPERATURE,
        help="Sampling temperature for the model",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    user_input = " ".join(args.user_input).strip()

    try:
        song_request = build_song_request(
            user_input,
            model=args.model,
            host=args.host,
            temperature=args.temperature,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(song_request.model_dump_json(indent=2))
    return 0


def _build_system_prompt() -> str:
    return build_structured_output_prompt(
        SEARCH_QUERY_BUILDER_INSTRUCTIONS,
        SongRequest,
    )


if __name__ == "__main__":
    raise SystemExit(main())
