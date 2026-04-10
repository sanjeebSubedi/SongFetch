from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from src.agents.download_selector.agent import (
    select_download_audio_request,
    select_fallback_download_audio_request,
)
from src.agents.metadata_request_builder.agent import build_metadata_lookup_request
from src.agents.metadata_selector.agent import select_metadata_match
from src.agents.search_query_builder.agent import build_song_request
from src.providers.itunes import (
    DEFAULT_ITUNES_BASE_URL,
    DEFAULT_ITUNES_COUNTRY,
    ITunesConfig,
)
from src.providers.lrclib import LRCLibConfig
from src.providers.ollama import (
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_TEMPERATURE,
)
from src.tools.download import download_song_audio
from src.tools.lyrics import fetch_lyrics
from src.tools.metadata import build_fallback_tag_metadata, fetch_music_metadata
from src.tools.search import search_song_audio
from src.tools.tagging import embed_selected_metadata
from src.types import LyricsResult, TagMetadata


def run_pipeline(
    user_input: str,
    *,
    model: str = DEFAULT_OLLAMA_MODEL,
    host: str = DEFAULT_OLLAMA_HOST,
    temperature: float = DEFAULT_OLLAMA_TEMPERATURE,
    search_limit: int = 5,
    metadata_limit: int = 5,
    itunes_base_url: str = DEFAULT_ITUNES_BASE_URL,
    itunes_country: str = DEFAULT_ITUNES_COUNTRY,
) -> dict[str, Any]:
    normalized_user_input = user_input.strip()
    if not normalized_user_input:
        raise ValueError("user_input must not be empty")

    _progress("1/9 Building song request from user input")
    song_request = build_song_request(
        normalized_user_input,
        model=model,
        host=host,
        temperature=temperature,
    )
    _progress("2/9 Searching YouTube candidates")
    search_results = search_song_audio(song_request.search_query, limit=search_limit)
    if not search_results:
        raise RuntimeError(
            "No YouTube search results were found for the generated query."
        )

    _progress("3/9 Building metadata lookup request from YouTube results")
    metadata_lookup_request = build_metadata_lookup_request(
        normalized_user_input,
        search_results,
        model=model,
        host=host,
        temperature=temperature,
    )
    _progress("4/9 Fetching metadata from iTunes Search API")
    itunes_config = ITunesConfig(
        base_url=itunes_base_url,
        country=itunes_country,
    )
    metadata_matches = fetch_music_metadata(
        metadata_lookup_request.song_name,
        artist=metadata_lookup_request.artist,
        limit=metadata_limit,
        config=itunes_config,
    )
    selected_metadata_model = None
    selected_download = None
    download_result = None
    tagging_result = None
    selected_download_model = None
    lyrics_result_model: LyricsResult | None = None
    tag_metadata: TagMetadata | None = None

    if metadata_matches:
        _progress("5/9 Selecting canonical metadata match")
        selected_metadata_model = select_metadata_match(
            normalized_user_input,
            metadata_matches,
            model=model,
            host=host,
            temperature=temperature,
        )
        _progress("6/9 Selecting best YouTube URL for download")
        selected_download_model = select_download_audio_request(
            normalized_user_input,
            selected_metadata_model,
            search_results,
            requested_format=song_request.format,
            model=model,
            host=host,
            temperature=temperature,
        )
        tag_metadata = TagMetadata(
            title=selected_metadata_model.title,
            artist=selected_metadata_model.artist,
            album=selected_metadata_model.album,
            artwork_url=selected_metadata_model.artwork_url,
        )
    else:
        _progress("5/9 No iTunes metadata found; switching to fallback selection")
        _progress("6/9 Selecting fallback YouTube candidate")
        selected_download_model = select_fallback_download_audio_request(
            normalized_user_input,
            search_results,
            requested_format=song_request.format,
            song_name=metadata_lookup_request.song_name,
            artist=metadata_lookup_request.artist,
        )
        selected_result = _find_search_result_by_url(
            search_results,
            selected_download_model.tool_call.parameters.url,
        )
        tag_metadata = build_fallback_tag_metadata(
            song_request,
            metadata_lookup_request,
            selected_result=selected_result,
        )

    if selected_download_model is not None:
        selected_download = selected_download_model.model_dump()
        _progress("7/9 Downloading audio")
        download_result = download_song_audio(
            selected_download_model.tool_call.parameters.url,
            audio_format=selected_download_model.tool_call.parameters.format,
            filename=selected_download_model.tool_call.parameters.filename,
        )
        if tag_metadata is not None:
            _progress("8/9 Looking up lyrics")
            lyrics_result_model = fetch_lyrics(
                tag_metadata,
                duration_seconds=_lyrics_duration_seconds(
                    selected_metadata_model=selected_metadata_model,
                    search_results=search_results,
                    selected_url=selected_download_model.tool_call.parameters.url,
                ),
                config=LRCLibConfig(),
            )
        if selected_metadata_model is not None:
            _progress("9/9 Embedding selected metadata tags")
            tagging_result = embed_selected_metadata(
                download_result["output_path"],
                selected_metadata_model,
                lyrics=(
                    lyrics_result_model.plain_lyrics
                    if lyrics_result_model is not None
                    else None
                ),
            )
        else:
            _progress("9/9 Embedding inferred metadata tags")
            tagging_result = embed_selected_metadata(
                download_result["output_path"],
                tag_metadata,
                lyrics=(
                    lyrics_result_model.plain_lyrics
                    if lyrics_result_model is not None
                    else None
                ),
            )

    return {
        "user_input": normalized_user_input,
        "song_request": song_request.model_dump(),
        "search_results": search_results,
        "metadata_lookup_request": metadata_lookup_request.model_dump(),
        "metadata_matches": metadata_matches,
        "selected_metadata": (
            selected_metadata_model.model_dump() if selected_metadata_model else None
        ),
        "selected_download": selected_download,
        "download_result": download_result,
        "lyrics_result": _serialize_lyrics_result(
            lyrics_result_model,
            lyrics_embedded=bool(
                tagging_result.get("lyrics_embedded")
                if isinstance(tagging_result, dict)
                else False
            ),
        ),
        "tagging_result": tagging_result,
    }


def _find_search_result_by_url(
    search_results: list[dict[str, Any]],
    url: str,
) -> dict[str, Any] | None:
    for result in search_results:
        if result.get("webpage_url") == url:
            return result
    return None


def _lyrics_duration_seconds(
    *,
    selected_metadata_model: Any,
    search_results: list[dict[str, Any]],
    selected_url: str,
) -> int | None:
    if selected_metadata_model is not None:
        duration_ms = getattr(selected_metadata_model, "duration_ms", None)
        if isinstance(duration_ms, int) and duration_ms > 0:
            return round(duration_ms / 1000)

    selected_result = _find_search_result_by_url(search_results, selected_url)
    if selected_result is None:
        return None

    duration_seconds = selected_result.get("duration_seconds")
    if isinstance(duration_seconds, int) and duration_seconds > 0:
        return duration_seconds
    return None


def _progress(message: str) -> None:
    print(f"[pipeline] {message}", file=sys.stderr)


def _serialize_lyrics_result(
    lyrics_result: LyricsResult | None,
    *,
    lyrics_embedded: bool,
) -> dict[str, Any]:
    if lyrics_result is None:
        return {
            "found": False,
            "source": "lrclib",
            "lyrics_embedded": False,
        }
    return {
        "found": lyrics_result.found,
        "source": lyrics_result.source,
        "synced_available": lyrics_result.synced_available,
        "synced_used": lyrics_result.synced_used,
        "lyrics_embedded": lyrics_embedded,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the song request pipeline through query building, YouTube search, "
            "iTunes metadata lookup, and audio download."
        )
    )
    parser.add_argument(
        "user_input",
        nargs="+",
        help="Natural-language request to send through the pipeline",
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
    parser.add_argument(
        "--search-limit",
        type=int,
        default=5,
        help="Number of YouTube matches to fetch",
    )
    parser.add_argument(
        "--metadata-limit",
        type=int,
        default=5,
        help="Number of metadata matches to fetch",
    )
    parser.add_argument(
        "--itunes-base-url",
        default=DEFAULT_ITUNES_BASE_URL,
        help="Base URL for the iTunes Search API",
    )
    parser.add_argument(
        "--itunes-country",
        default=DEFAULT_ITUNES_COUNTRY,
        help="Storefront country code for the iTunes Search API",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        result = run_pipeline(
            " ".join(args.user_input),
            model=args.model,
            host=args.host,
            temperature=args.temperature,
            search_limit=args.search_limit,
            metadata_limit=args.metadata_limit,
            itunes_base_url=args.itunes_base_url,
            itunes_country=args.itunes_country,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
