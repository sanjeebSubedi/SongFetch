from __future__ import annotations

import re

from src.agents.metadata_request_builder.agent import (
    build_metadata_lookup_request,
)
from src.agents.metadata_request_builder.schema import MetadataLookupRequest
from src.agents.search_query_builder.schema import SongRequest
from src.providers.ollama import (
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_TEMPERATURE,
)
from src.providers.itunes import (
    ITunesConfig,
    search_songs,
)
from src.providers.spotify import (
    SpotifyConfig,
    search_tracks as search_spotify_tracks,
)
from src.types import MusicMetadataResult, SearchResult, TagMetadata


def fetch_music_metadata(
    song_name: str,
    *,
    artist: str | None = None,
    album: str | None = None,
    limit: int = 5,
    config: ITunesConfig | None = None,
) -> list[MusicMetadataResult]:
    metadata_query = _build_itunes_query(
        song_name,
        artist=artist,
        album=album,
    )
    payload = search_songs(
        metadata_query,
        limit=limit,
        config=config,
    )
    return _normalize_results(payload)


def fetch_metadata_from_request(
    song_request: SongRequest,
    *,
    limit: int = 5,
    config: ITunesConfig | None = None,
) -> list[MusicMetadataResult]:
    return fetch_music_metadata(
        song_request.song_name,
        artist=song_request.artist,
        album=song_request.album,
        limit=limit,
        config=config,
    )


def fetch_metadata_from_search_results(
    user_input: str,
    search_results: list[SearchResult],
    *,
    model: str = DEFAULT_OLLAMA_MODEL,
    host: str = DEFAULT_OLLAMA_HOST,
    temperature: float = DEFAULT_OLLAMA_TEMPERATURE,
    limit: int = 5,
    config: ITunesConfig | None = None,
) -> list[MusicMetadataResult]:
    metadata_lookup_request = build_metadata_lookup_request(
        user_input,
        search_results,
        model=model,
        host=host,
        temperature=temperature,
    )
    return fetch_music_metadata(
        metadata_lookup_request.song_name,
        artist=metadata_lookup_request.artist,
        limit=limit,
        config=config,
    )


def fetch_spotify_metadata(
    song_name: str,
    *,
    artist: str | None = None,
    album: str | None = None,
    limit: int = 5,
    config: SpotifyConfig | None = None,
) -> list[MusicMetadataResult]:
    normalized_song_name = song_name.strip()
    if not normalized_song_name:
        raise ValueError("song_name must not be empty")

    return search_spotify_tracks(
        normalized_song_name,
        artist=artist,
        album=album,
        limit=limit,
        config=config,
    )


def build_fallback_tag_metadata(
    song_request: SongRequest,
    metadata_lookup_request: MetadataLookupRequest,
    *,
    selected_result: SearchResult | None = None,
) -> TagMetadata:
    title = _first_non_empty(
        metadata_lookup_request.song_name,
        song_request.song_name,
        _extract_title_from_result(selected_result),
        "Unknown Title",
    )
    artist = _first_non_empty(
        metadata_lookup_request.artist,
        song_request.artist,
        _normalize_uploader(selected_result.get("uploader") if selected_result else None),
    )
    album = _first_non_empty(
        song_request.album,
        _extract_album_from_result(selected_result),
    )
    return TagMetadata(
        title=title,
        artist=artist,
        album=album,
        genre=None,
        track_number=None,
        disc_number=None,
        artwork_url=None,
    )


def _build_itunes_query(
    song_name: str,
    *,
    artist: str | None = None,
    album: str | None = None,
) -> str:
    normalized_song_name = song_name.strip()
    if not normalized_song_name:
        raise ValueError("song_name must not be empty")

    parts = [normalized_song_name]
    if artist and artist.strip():
        parts.append(artist.strip())
    if album and album.strip():
        parts.append(album.strip())
    return " ".join(parts)


def _normalize_results(payload: dict[str, object]) -> list[MusicMetadataResult]:
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        return []

    return [
        _normalize_result(result)
        for result in raw_results
        if isinstance(result, dict) and _optional_int(result.get("trackId")) is not None
    ]


def _normalize_result(result: dict[str, object]) -> MusicMetadataResult:
    track_id = _optional_int(result.get("trackId"))
    if track_id is None:
        raise ValueError("iTunes result must include trackId")

    track_explicitness = _optional_text(result.get("trackExplicitness"))
    return {
        "provider": "itunes",
        "provider_track_id": str(track_id),
        "provider_collection_id": _optional_string_int(result.get("collectionId")),
        "title": _optional_text(result.get("trackName")),
        "artist": _optional_text(result.get("artistName")),
        "album": _optional_text(result.get("collectionName")),
        "release_date": _optional_text(result.get("releaseDate")),
        "duration_ms": _optional_int(result.get("trackTimeMillis")),
        "explicitness": track_explicitness,
        "is_explicit": _is_explicit(track_explicitness),
        "track_number": _optional_int(result.get("trackNumber")),
        "disc_number": _optional_int(result.get("discNumber")),
        "genre": _optional_text(result.get("primaryGenreName")),
        "artwork_url": _optional_text(result.get("artworkUrl100")),
        "preview_url": _optional_text(result.get("previewUrl")),
        "track_view_url": _optional_text(result.get("trackViewUrl")),
        "collection_view_url": _optional_text(result.get("collectionViewUrl")),
    }


def _first_non_empty(*values: str | None) -> str | None:
    for value in values:
        if not isinstance(value, str):
            continue
        normalized = value.strip()
        if normalized:
            return normalized
    return None


def _normalize_uploader(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    normalized = re.sub(r"\s*-\s*topic$", "", normalized, flags=re.IGNORECASE)
    return normalized.strip() or None


def _extract_title_from_result(selected_result: SearchResult | None) -> str | None:
    if not selected_result:
        return None
    title = _optional_text(selected_result.get("title"))
    if not title:
        return None
    normalized = re.sub(r"\[[^\]]+\]|\([^)]+\)", "", title)
    if " - " in normalized:
        _, maybe_title = normalized.split(" - ", maxsplit=1)
        normalized = maybe_title
    normalized = re.sub(
        r"\b(official video|official audio|lyrics?|lyric video|audio)\b",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"\s+", " ", normalized).strip(" -")
    return normalized or title


def _extract_album_from_result(selected_result: SearchResult | None) -> str | None:
    if not selected_result:
        return None

    description = _optional_text(selected_result.get("description"))
    if description:
        patterns = (
            r"(?i)\bfrom the album\b[:\s\"'-]*([^\n|]+)",
            r"(?i)\balbum\b[:\s\"'-]*([^\n|]+)",
        )
        for pattern in patterns:
            match = re.search(pattern, description)
            if not match:
                continue
            candidate = re.split(r"[|.]", match.group(1), maxsplit=1)[0].strip(" \"'-")
            if candidate:
                return candidate
    return None


def _is_explicit(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized == "explicit":
        return True
    if normalized in {"notexplicit", "cleaned"}:
        return False
    return None


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized


def _optional_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _optional_string_int(value: object) -> str | None:
    converted = _optional_int(value)
    return str(converted) if converted is not None else None
