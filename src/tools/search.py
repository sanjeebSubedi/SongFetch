from __future__ import annotations

from src.agents.search_query_builder.agent import build_song_request
from src.providers.ollama import (
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_TEMPERATURE,
)
from src.tools._shared import (
    build_cookies_from_browser,
    build_yt_dlp_runtime_options,
    get_yt_dlp,
)
from src.types import SearchResult


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
        "ignoreerrors": True,
    }
    cookies_from_browser = build_cookies_from_browser()
    if cookies_from_browser is not None:
        search_options["cookiesfrombrowser"] = cookies_from_browser
    search_options.update(build_yt_dlp_runtime_options())

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
                "description": entry.get("description"),
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
