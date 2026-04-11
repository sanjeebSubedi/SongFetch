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
    normalized_user_input = user_input.strip()
    if not normalized_user_input:
        raise ValueError("user_input must not be empty")

    _progress("1/10 Building song request from user input")
    song_request = build_song_request(
        normalized_user_input,
        model=model,
        host=host,
        temperature=temperature,
    )
    _progress("2/10 Searching YouTube candidates")
    search_results = search_song_audio(song_request.search_query, limit=search_limit)
    if not search_results:
        raise RuntimeError(
            "No YouTube search results were found for the generated query."
        )

    _progress("3/10 Building metadata lookup request from YouTube results")
    metadata_lookup_request = build_metadata_lookup_request(
        normalized_user_input,
        search_results,
        model=model,
        host=host,
        temperature=temperature,
    )
    _progress("4/10 Fetching metadata from iTunes Search API")
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
    if not metadata_matches:
        _progress("5/10 No iTunes metadata found; trying Spotify metadata")
        metadata_matches = fetch_spotify_metadata(
            metadata_lookup_request.song_name,
            artist=metadata_lookup_request.artist,
            limit=metadata_limit,
            config=SpotifyConfig(),
        )

    selected_metadata_model = None
    selected_download = None
    download_result = None
    tagging_result = None
    selected_download_model = None
    lyrics_result_model: LyricsResult | None = None
    tag_metadata: TagMetadata | None = None
    download_selection_source: str | None = None

    if metadata_matches:
        _progress("6/10 Selecting canonical metadata match")
        selected_metadata_model = select_metadata_match(
            normalized_user_input,
            metadata_matches,
            model=model,
            host=host,
            temperature=temperature,
        )
        _progress("7/10 Selecting best YouTube URL for download")
        try:
            selected_download_model = select_download_audio_request(
                normalized_user_input,
                selected_metadata_model,
                search_results,
                requested_format=song_request.format,
                model=model,
                host=host,
                temperature=temperature,
            )
            download_selection_source = "metadata_selector"
        except Exception as exc:
            _progress(
                f"7/10 Metadata-backed selection failed; using fallback selector ({exc})"
            )
            selected_download_model = select_fallback_download_audio_request(
                normalized_user_input,
                search_results,
                requested_format=song_request.format,
                song_name=selected_metadata_model.title,
                artist=selected_metadata_model.artist,
            )
            download_selection_source = "fallback_selector"
        tag_metadata = TagMetadata(
            title=selected_metadata_model.title,
            artist=selected_metadata_model.artist,
            album=selected_metadata_model.album,
            genre=selected_metadata_model.genre,
            track_number=selected_metadata_model.track_number,
            disc_number=selected_metadata_model.disc_number,
            artwork_url=selected_metadata_model.artwork_url,
        )
    else:
        _progress("6/10 No provider metadata found; switching to fallback selection")
        _progress("7/10 Selecting fallback YouTube candidate")
        selected_download_model = select_fallback_download_audio_request(
            normalized_user_input,
            search_results,
            requested_format=song_request.format,
            song_name=metadata_lookup_request.song_name,
            artist=metadata_lookup_request.artist,
        )
        download_selection_source = "fallback_selector"
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
        _progress("8/10 Downloading audio")
        download_result = download_song_audio(
            selected_download_model.tool_call.parameters.url,
            audio_format=selected_download_model.tool_call.parameters.format,
            filename=selected_download_model.tool_call.parameters.filename,
        )
        if tag_metadata is not None:
            _progress("9/10 Looking up lyrics")
            try:
                lyrics_result_model = fetch_lyrics(
                    tag_metadata,
                    duration_seconds=_lyrics_duration_seconds(
                        selected_metadata_model=selected_metadata_model,
                        search_results=search_results,
                        selected_url=selected_download_model.tool_call.parameters.url,
                    ),
                    config=LRCLibConfig(),
                )
            except Exception as exc:
                _progress(
                    f"9/10 Lyrics lookup failed; continuing without lyrics ({exc})"
                )
                lyrics_result_model = None
        _progress("10/10 Embedding metadata tags")
        tagging_target = selected_metadata_model or tag_metadata
        tagging_result = embed_selected_metadata(
            download_result["output_path"],
            tagging_target,
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
        "metadata_source": _metadata_source(selected_metadata_model),
        "download_selection_source": download_selection_source,
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
