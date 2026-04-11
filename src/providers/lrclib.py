from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request

from src.types import LyricsResult

DEFAULT_LRCLIB_BASE_URL = "https://lrclib.net/api"
DEFAULT_LRCLIB_TIMEOUT_SECONDS = 10.0
DEFAULT_LRCLIB_USER_AGENT = os.environ.get(
    "LRCLIB_USER_AGENT",
    "audio-agent/0.1.0",
)


@dataclass(frozen=True, slots=True)
class LRCLibConfig:
    base_url: str = DEFAULT_LRCLIB_BASE_URL
    timeout_seconds: float = DEFAULT_LRCLIB_TIMEOUT_SECONDS
    user_agent: str = DEFAULT_LRCLIB_USER_AGENT


def lookup_lyrics(
    title: str,
    *,
    artist: str | None = None,
    album: str | None = None,
    duration_seconds: int | None = None,
    config: LRCLibConfig | None = None,
) -> LyricsResult | None:
    normalized_title = title.strip()
    if not normalized_title:
        raise ValueError("title must not be empty")

    active_config = config or LRCLibConfig()
    exact_payload = _get_exact_match(
        normalized_title,
        artist=artist,
        album=album,
        duration_seconds=duration_seconds,
        config=active_config,
    )
    if exact_payload is not None:
        return _normalize_lyrics_payload(exact_payload)

    search_payload = _search_lyrics(
        normalized_title,
        artist=artist,
        album=album,
        config=active_config,
    )
    if not search_payload:
        return None

    best_candidate = _select_best_search_candidate(
        search_payload,
        title=normalized_title,
        artist=artist,
        album=album,
        duration_seconds=duration_seconds,
    )
    if best_candidate is None:
        return None
    return _normalize_lyrics_payload(best_candidate)


def _get_exact_match(
    title: str,
    *,
    artist: str | None,
    album: str | None,
    duration_seconds: int | None,
    config: LRCLibConfig,
) -> dict[str, Any] | None:
    params: dict[str, object] = {"track_name": title}
    if artist and artist.strip():
        params["artist_name"] = artist.strip()
    if album and album.strip():
        params["album_name"] = album.strip()
    if duration_seconds is not None and duration_seconds > 0:
        params["duration"] = duration_seconds

    payload = _request_json("/get", params=params, config=config, allow_not_found=True)
    return payload if isinstance(payload, dict) else None


def _search_lyrics(
    title: str,
    *,
    artist: str | None,
    album: str | None,
    config: LRCLibConfig,
) -> list[dict[str, Any]]:
    params: dict[str, object] = {"track_name": title}
    if artist and artist.strip():
        params["artist_name"] = artist.strip()
    if album and album.strip():
        params["album_name"] = album.strip()

    payload = _request_json("/search", params=params, config=config, allow_not_found=True)
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _request_json(
    path: str,
    *,
    params: dict[str, object],
    config: LRCLibConfig,
    allow_not_found: bool,
) -> dict[str, Any] | list[dict[str, Any]] | None:
    query_string = parse.urlencode(
        {key: value for key, value in params.items() if value is not None}
    )
    url = f"{config.base_url.rstrip('/')}{path}?{query_string}"
    raw_request = request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": config.user_agent,
        },
        method="GET",
    )

    try:
        with request.urlopen(raw_request, timeout=config.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        if allow_not_found and exc.code == 404:
            return None
        return None
    except (TimeoutError, OSError, error.URLError, json.JSONDecodeError):
        return None


def _select_best_search_candidate(
    candidates: list[dict[str, Any]],
    *,
    title: str,
    artist: str | None,
    album: str | None,
    duration_seconds: int | None,
) -> dict[str, Any] | None:
    if not candidates:
        return None

    normalized_title = _normalize_text(title)
    normalized_artist = _normalize_text(artist) if artist else None
    normalized_album = _normalize_text(album) if album else None

    scored = sorted(
        candidates,
        key=lambda candidate: _candidate_score(
            candidate,
            normalized_title=normalized_title,
            normalized_artist=normalized_artist,
            normalized_album=normalized_album,
            duration_seconds=duration_seconds,
        ),
        reverse=True,
    )
    best_candidate = scored[0]
    if _extract_plain_lyrics(best_candidate) is None:
        return None
    return best_candidate


def _candidate_score(
    candidate: dict[str, Any],
    *,
    normalized_title: str,
    normalized_artist: str | None,
    normalized_album: str | None,
    duration_seconds: int | None,
) -> tuple[int, int, int, int]:
    candidate_title = _normalize_text(candidate.get("trackName"))
    candidate_artist = _normalize_text(candidate.get("artistName"))
    candidate_album = _normalize_text(candidate.get("albumName"))
    has_plain = _extract_plain_lyrics(candidate) is not None
    synced_available = isinstance(candidate.get("syncedLyrics"), str) and bool(
        candidate.get("syncedLyrics", "").strip()
    )
    candidate_duration = _coerce_int(candidate.get("duration"))

    title_score = 2 if candidate_title == normalized_title else int(
        normalized_title in candidate_title or candidate_title in normalized_title
    )
    artist_score = 0
    if normalized_artist:
        artist_score = 2 if candidate_artist == normalized_artist else int(
            normalized_artist in candidate_artist or candidate_artist in normalized_artist
        )
    album_score = 0
    if normalized_album:
        album_score = 1 if candidate_album == normalized_album else 0
    duration_score = 0
    if duration_seconds is not None and candidate_duration is not None:
        duration_score = -abs(candidate_duration - duration_seconds)

    return (
        int(has_plain),
        synced_available,
        title_score + artist_score + album_score,
        duration_score,
    )


def _normalize_lyrics_payload(payload: dict[str, Any]) -> LyricsResult | None:
    plain_lyrics = _extract_plain_lyrics(payload)
    if plain_lyrics is None:
        return None
    synced_lyrics = payload.get("syncedLyrics")
    synced_available = isinstance(synced_lyrics, str) and bool(synced_lyrics.strip())
    synced_used = not isinstance(payload.get("plainLyrics"), str) or not payload.get(
        "plainLyrics", ""
    ).strip()
    return LyricsResult(
        plain_lyrics=plain_lyrics,
        source="lrclib",
        found=True,
        synced_available=synced_available,
        synced_used=synced_used and synced_available,
    )


def _extract_plain_lyrics(payload: dict[str, Any]) -> str | None:
    plain_lyrics = payload.get("plainLyrics")
    if isinstance(plain_lyrics, str) and plain_lyrics.strip():
        return plain_lyrics.strip()

    synced_lyrics = payload.get("syncedLyrics")
    if isinstance(synced_lyrics, str) and synced_lyrics.strip():
        stripped = _strip_synced_timestamps(synced_lyrics)
        if stripped:
            return stripped
    return None


def _strip_synced_timestamps(value: str) -> str:
    stripped_lines: list[str] = []
    for raw_line in value.splitlines():
        cleaned_line = re.sub(r"\[[0-9:.]+\]", "", raw_line).strip()
        if cleaned_line:
            stripped_lines.append(cleaned_line)
    return "\n".join(stripped_lines).strip()


def _normalize_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    normalized = value.casefold().strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _coerce_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None
