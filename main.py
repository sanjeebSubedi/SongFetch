from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from src.agents.download_selector.agent import select_download_audio_request
from src.agents.metadata_request_builder.agent import build_metadata_lookup_request
from src.agents.metadata_selector.agent import select_metadata_match
from src.agents.search_query_builder.agent import build_song_request
from src.providers.musicbrainz import (
    DEFAULT_MUSICBRAINZ_BASE_URL,
    DEFAULT_MUSICBRAINZ_USER_AGENT,
    MusicBrainzConfig,
)
from src.providers.ollama import (
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_TEMPERATURE,
)
from src.tools.download import download_song_audio
from src.tools.metadata import fetch_music_metadata
from src.tools.search import search_song_audio
from src.tools.tagging import embed_selected_metadata


def run_pipeline(
    user_input: str,
    *,
    model: str = DEFAULT_OLLAMA_MODEL,
    host: str = DEFAULT_OLLAMA_HOST,
    temperature: float = DEFAULT_OLLAMA_TEMPERATURE,
    search_limit: int = 5,
    metadata_limit: int = 5,
    musicbrainz_base_url: str = DEFAULT_MUSICBRAINZ_BASE_URL,
    musicbrainz_user_agent: str = DEFAULT_MUSICBRAINZ_USER_AGENT,
) -> dict[str, Any]:
    normalized_user_input = user_input.strip()
    if not normalized_user_input:
        raise ValueError("user_input must not be empty")

    _progress("1/8 Building song request from user input")
    song_request = build_song_request(
        normalized_user_input,
        model=model,
        host=host,
        temperature=temperature,
    )
    _progress("2/8 Searching YouTube candidates")
    search_results = search_song_audio(song_request.search_query, limit=search_limit)
    if not search_results:
        raise RuntimeError(
            "No YouTube search results were found for the generated query."
        )

    _progress("3/8 Building metadata lookup request from YouTube results")
    metadata_lookup_request = build_metadata_lookup_request(
        normalized_user_input,
        search_results,
        model=model,
        host=host,
        temperature=temperature,
    )
    _progress("4/8 Fetching metadata from MusicBrainz")
    musicbrainz_config = MusicBrainzConfig(
        base_url=musicbrainz_base_url,
        user_agent=musicbrainz_user_agent,
    )
    metadata_matches = fetch_music_metadata(
        metadata_lookup_request.song_name,
        artist=metadata_lookup_request.artist,
        limit=metadata_limit,
        config=musicbrainz_config,
    )
    selected_metadata_model = None
    selected_download = None
    download_result = None
    tagging_result = None

    if metadata_matches:
        _progress("5/8 Selecting canonical metadata match")
        selected_metadata_model = select_metadata_match(
            normalized_user_input,
            metadata_matches,
            model=model,
            host=host,
            temperature=temperature,
        )
        _progress("6/8 Selecting best YouTube URL for download")
        selected_download_model = select_download_audio_request(
            normalized_user_input,
            selected_metadata_model,
            search_results,
            requested_format=song_request.format,
            model=model,
            host=host,
            temperature=temperature,
        )
        selected_download = selected_download_model.model_dump()
        _progress("7/8 Downloading audio")
        download_result = download_song_audio(
            selected_download_model.tool_call.parameters.url,
            audio_format=selected_download_model.tool_call.parameters.format,
            filename=selected_download_model.tool_call.parameters.filename,
        )
        _progress("8/8 Embedding selected metadata tags")
        tagging_result = embed_selected_metadata(
            download_result["output_path"],
            selected_metadata_model,
        )
    else:
        _progress("5/8 No metadata matches found; skipping selection and download")

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
        "tagging_result": tagging_result,
    }


def _progress(message: str) -> None:
    print(f"[pipeline] {message}", file=sys.stderr)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the song request pipeline through query building, YouTube search, "
            "MusicBrainz metadata lookup, and audio download."
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
        help="Number of MusicBrainz matches to fetch",
    )
    parser.add_argument(
        "--musicbrainz-base-url",
        default=DEFAULT_MUSICBRAINZ_BASE_URL,
        help="Base URL for the MusicBrainz web service",
    )
    parser.add_argument(
        "--musicbrainz-user-agent",
        default=DEFAULT_MUSICBRAINZ_USER_AGENT,
        help="User-Agent header to send to MusicBrainz",
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
            musicbrainz_base_url=args.musicbrainz_base_url,
            musicbrainz_user_agent=args.musicbrainz_user_agent,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# {'id': 'o_v9MY_FMcw', 'title': 'One Direction - Best Song Ever', 'uploader': 'One Direction', 'duration_seconds': 373, 'webpage_url': 'https://www.youtube.com/watch?v=o_v9MY_FMcw', 'view_count': 826542298}
# {'id': '-zCF1-emakY', 'title': 'One Direction - Best Song Ever (Audio)', 'uploader': 'One Direction', 'duration_seconds': 200, 'webpage_url': 'https://www.youtube.com/watch?v=-zCF1-emakY', 'view_count': 19767941}
# {'id': 'UGKl2kigv88', 'title': 'Best Song Ever - One Direction (Lyrics) 🎵', 'uploader': 'Pillow', 'duration_seconds': 195, 'webpage_url': 'https://www.youtube.com/watch?v=UGKl2kigv88', 'view_count': 1835930}
# {'id': 'n1d3dFDc1kc', 'title': 'THE GREATEST SONG EVER MADE', 'uploader': 'Pleasantries', 'duration_seconds': 233, 'webpage_url': 'https://www.youtube.com/watch?v=n1d3dFDc1kc', 'view_count': 5450433}
# {'id': 'TQ_juYXT4so', 'title': 'One Direction - Best Song Ever (Audio)', 'uploader': 'One Direction', 'duration_seconds': 202, 'webpage_url': 'https://www.youtube.com/watch?v=TQ_juYXT4so', 'view_count': 672909}

# {
#     "recording_id": "c00be91a-f6d9-4e76-afe3-b18862289617",
#     "release_group_id": "5dd51c1a-8729-4e5c-ba28-81762d94a1b5",
#     "release_group_primary_type": "Album",
#     "release_group_secondary_types": ["Compilation"],
#     "release_status": "Official",
#     "title": "Best Song Ever",
#     "artist": "One Direction",
#     "artist_credit": "One Direction",
#     "album": "Dance Party 2014",
#     "first_release_date": "2014",
#     "length_ms": 371000,
#     "score": 100,
#     "disambiguation": "music video",
#     "musicbrainz_url": "https://musicbrainz.org/recording/c00be91a-f6d9-4e76-afe3-b18862289617",
# }

# {
#     "recording_id": "43341f5d-14f8-49aa-8d99-d81de44fb9c3",
#     "release_group_id": "f98f6fb2-0ce2-467a-a32c-2da684b8d9bb",
#     "release_group_primary_type": "Single",
#     "release_group_secondary_types": None,
#     "release_status": "Official",
#     "title": "Best Song Ever",
#     "artist": "One Direction",
#     "artist_credit": "One Direction",
#     "album": "Best Song Ever (From THIS IS US)",
#     "first_release_date": "2013-07-22",
#     "length_ms": 200106,
#     "score": 100,
#     "disambiguation": None,
#     "musicbrainz_url": "https://musicbrainz.org/recording/43341f5d-14f8-49aa-8d99-d81de44fb9c3",
# }
