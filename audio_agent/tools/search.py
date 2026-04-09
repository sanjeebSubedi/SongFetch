from __future__ import annotations

import argparse
import json
import sys

from audio_agent.agents.search_query_builder.agent import build_song_request
from audio_agent.providers.ollama import (
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_TEMPERATURE,
)
from audio_agent.tools._shared import get_yt_dlp
from audio_agent.types import SearchResult


def search_song_audio(query: str, limit: int = 5) -> list[SearchResult]:
    """Search YouTube with yt-dlp and return candidate songs for an LLM tool."""
    search_query = query.strip()
    if not search_query:
        raise ValueError("query must not be empty")

    search_options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }

    yt_dlp = get_yt_dlp()
    with yt_dlp.YoutubeDL(search_options) as ydl:
        result = ydl.extract_info(
            f"ytsearch{max(1, limit)}:{search_query}",
            download=False,
        )

    matches: list[SearchResult] = []
    for entry in result.get("entries", []):
        if not isinstance(entry, dict):
            continue

        video_id = entry.get("id")
        webpage_url = entry.get("webpage_url")
        if not webpage_url and video_id:
            webpage_url = f"https://www.youtube.com/watch?v={video_id}"

        matches.append(
            {
                "id": video_id,
                "title": entry.get("title"),
                "uploader": entry.get("uploader") or entry.get("channel"),
                "duration_seconds": entry.get("duration"),
                "webpage_url": webpage_url,
                "view_count": entry.get("view_count"),
            }
        )

    return matches


def search_from_request(
    user_input: str,
    *,
    model: str = DEFAULT_OLLAMA_MODEL,
    host: str = DEFAULT_OLLAMA_HOST,
    temperature: float = DEFAULT_OLLAMA_TEMPERATURE,
    limit: int = 5,
) -> list[SearchResult]:
    """Build a search query from natural language, then search with yt-dlp."""
    song_request = build_song_request(
        user_input,
        model=model,
        host=host,
        temperature=temperature,
    )
    return search_song_audio(song_request.search_query, limit=limit)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search YouTube with yt-dlp and print candidate matches as JSON."
    )
    parser.add_argument(
        "query",
        nargs="+",
        help="Natural-language song request, or a direct search query with --direct-query",
    )
    parser.add_argument(
        "--direct-query",
        action="store_true",
        help="Treat the input as a raw YouTube search query and skip the LLM query builder",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Number of matches to return",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_OLLAMA_MODEL,
        help="Ollama model name to use when building a search query",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_OLLAMA_HOST,
        help="Host for the Ollama server when building a search query",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=DEFAULT_OLLAMA_TEMPERATURE,
        help="Sampling temperature for the query builder model",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    query = " ".join(args.query).strip()

    try:
        if args.direct_query:
            matches = search_song_audio(query, limit=args.limit)
        else:
            matches = search_from_request(
                query,
                model=args.model,
                host=args.host,
                temperature=args.temperature,
                limit=args.limit,
            )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(matches, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
