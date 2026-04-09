from __future__ import annotations

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
