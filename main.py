from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
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
from src.providers.spotify import SpotifyConfig
from src.pipeline import PipelineConfig, PipelineDependencies, SongPipelineController
from src.tools.download import download_song_audio
from src.tools.lyrics import fetch_lyrics
from src.tools.metadata import (
    build_fallback_tag_metadata,
    fetch_music_metadata,
    fetch_spotify_metadata,
)
from src.tools.search import search_song_audio
from src.tools.spotify import import_spotify_playlist_tracks
from src.tools.tagging import embed_selected_metadata
from src.types import LyricsResult, PlaylistTrack, TagMetadata


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
    controller = SongPipelineController(
        deps=PipelineDependencies(
            build_song_request=build_song_request,
            search_song_audio=search_song_audio,
            build_metadata_lookup_request=build_metadata_lookup_request,
            fetch_music_metadata=fetch_music_metadata,
            fetch_spotify_metadata=fetch_spotify_metadata,
            select_metadata_match=select_metadata_match,
            select_download_audio_request=select_download_audio_request,
            select_fallback_download_audio_request=select_fallback_download_audio_request,
            download_song_audio=download_song_audio,
            fetch_lyrics=fetch_lyrics,
            embed_selected_metadata=embed_selected_metadata,
            build_fallback_tag_metadata=build_fallback_tag_metadata,
        ),
        config=PipelineConfig(
            model=model,
            host=host,
            temperature=temperature,
            search_limit=search_limit,
            metadata_limit=metadata_limit,
        ),
        progress=_progress,
    )
    return controller.run(user_input)


def run_spotify_playlist_pipeline(
    playlist_ref: str,
    *,
    model: str = DEFAULT_OLLAMA_MODEL,
    host: str = DEFAULT_OLLAMA_HOST,
    temperature: float = DEFAULT_OLLAMA_TEMPERATURE,
    search_limit: int = 5,
    metadata_limit: int = 5,
    itunes_base_url: str = DEFAULT_ITUNES_BASE_URL,
    itunes_country: str = DEFAULT_ITUNES_COUNTRY,
    spotify_config: SpotifyConfig | None = None,
) -> dict[str, Any]:
    playlist = import_spotify_playlist_tracks(
        playlist_ref,
        config=spotify_config or SpotifyConfig(),
    )
    tracks = playlist.get("tracks")
    normalized_tracks = tracks if isinstance(tracks, list) else []

    results: list[dict[str, Any]] = []
    total_tracks = len(normalized_tracks)
    for index, track in enumerate(normalized_tracks, start=1):
        if not isinstance(track, PlaylistTrack):
            continue
        user_input = _playlist_track_to_user_input(track)
        _progress(
            f"playlist {index}/{total_tracks} Processing {track.artist} - {track.title}"
        )
        try:
            track_result = run_pipeline(
                user_input,
                model=model,
                host=host,
                temperature=temperature,
                search_limit=search_limit,
                metadata_limit=metadata_limit,
                itunes_base_url=itunes_base_url,
                itunes_country=itunes_country,
            )
            error_message = None
        except Exception as exc:
            track_result = None
            error_message = str(exc)
        results.append(
            {
                "index": index,
                "playlist_track": asdict(track),
                "result": track_result,
                "error": error_message,
            }
        )

    return {
        "playlist": {
            "playlist_id": playlist.get("playlist_id"),
            "name": playlist.get("name"),
            "spotify_url": playlist.get("spotify_url"),
        },
        "tracks": results,
        "summary": _summarize_playlist_results(results),
    }


def _find_search_result_by_url(
    search_results: list[dict[str, Any]],
    url: str,
) -> dict[str, Any] | None:
    for result in search_results:
        if result.get("webpage_url") == url:
            return result
    return None


def _metadata_source(selected_metadata_model: Any) -> str:
    if selected_metadata_model is None:
        return "fallback"
    provider = getattr(selected_metadata_model, "provider", None)
    return provider if isinstance(provider, str) and provider else "fallback"


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
    if (
        isinstance(duration_seconds, (int, float))
        and not isinstance(duration_seconds, bool)
        and duration_seconds > 0
    ):
        return round(duration_seconds)
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


def _playlist_track_to_user_input(track: PlaylistTrack) -> str:
    if track.album:
        return (
            f'download "{track.title}" by {track.artist} from the album {track.album}'
        )
    return f'download "{track.title}" by {track.artist}'


def _summarize_playlist_results(results: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "total": len(results),
        "downloaded": 0,
        "metadata_from_itunes": 0,
        "metadata_from_spotify": 0,
        "fallback_only": 0,
        "failed": 0,
    }
    for item in results:
        result = item.get("result")
        error_message = item.get("error")
        if isinstance(error_message, str) and error_message:
            summary["failed"] += 1
            continue
        if not isinstance(result, dict):
            summary["failed"] += 1
            continue
        if result.get("download_result"):
            summary["downloaded"] += 1
        else:
            summary["failed"] += 1

        metadata_source = result.get("metadata_source")
        if metadata_source == "itunes":
            summary["metadata_from_itunes"] += 1
        elif metadata_source == "spotify":
            summary["metadata_from_spotify"] += 1
        else:
            summary["fallback_only"] += 1
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the song request pipeline through query building, YouTube search, "
            "metadata lookup with iTunes and Spotify fallback, and audio download."
        )
    )
    parser.add_argument(
        "user_input",
        nargs="*",
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
    parser.add_argument(
        "--spotify-playlist",
        help="Public Spotify playlist URL or playlist ID to process sequentially",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.spotify_playlist:
            result = run_spotify_playlist_pipeline(
                args.spotify_playlist,
                model=args.model,
                host=args.host,
                temperature=args.temperature,
                search_limit=args.search_limit,
                metadata_limit=args.metadata_limit,
                itunes_base_url=args.itunes_base_url,
                itunes_country=args.itunes_country,
            )
        else:
            if not args.user_input:
                parser.error(
                    "user_input is required unless --spotify-playlist is provided"
                )
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
