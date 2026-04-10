from __future__ import annotations

import re

from src.agents.metadata_request_builder.agent import (
    build_metadata_lookup_request,
)
from src.agents.search_query_builder.schema import SongRequest
from src.providers.ollama import (
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_TEMPERATURE,
)
from src.providers.musicbrainz import (
    MusicBrainzConfig,
    search_recordings,
)
from src.types import MusicMetadataResult, SearchResult


def fetch_music_metadata(
    song_name: str,
    *,
    artist: str | None = None,
    album: str | None = None,
    limit: int = 5,
    config: MusicBrainzConfig | None = None,
) -> list[MusicMetadataResult]:
    metadata_query = _build_musicbrainz_query(
        song_name,
        artist=artist,
        album=album,
    )
    payload = search_recordings(
        metadata_query,
        limit=limit,
        config=config,
    )
    return _normalize_recordings(payload)


def fetch_metadata_from_request(
    song_request: SongRequest,
    *,
    limit: int = 5,
    config: MusicBrainzConfig | None = None,
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
    config: MusicBrainzConfig | None = None,
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


def _build_musicbrainz_query(
    song_name: str,
    *,
    artist: str | None = None,
    album: str | None = None,
) -> str:
    normalized_song_name = song_name.strip()
    if not normalized_song_name:
        raise ValueError("song_name must not be empty")

    parts = [f'recording:"{_escape_query_value(normalized_song_name)}"']
    if artist and artist.strip():
        parts.append(f'artist:"{_escape_query_value(artist.strip())}"')
    if album and album.strip():
        parts.append(f'release:"{_escape_query_value(album.strip())}"')
    return " AND ".join(parts)


def _escape_query_value(value: str) -> str:
    return re.sub(r'(["\\\\])', r"\\\1", value)


def _normalize_recordings(payload: dict[str, object]) -> list[MusicMetadataResult]:
    raw_recordings = payload.get("recordings")
    if not isinstance(raw_recordings, list):
        return []

    return [
        _normalize_recording(recording)
        for recording in raw_recordings
        if isinstance(recording, dict) and isinstance(recording.get("id"), str)
    ]


def _normalize_recording(recording: dict[str, object]) -> MusicMetadataResult:
    recording_id = str(recording["id"])
    releases = recording.get("releases")
    primary_release = releases[0] if isinstance(releases, list) and releases else {}
    if not isinstance(primary_release, dict):
        primary_release = {}
    release_group = primary_release.get("release-group")
    if not isinstance(release_group, dict):
        release_group = {}

    return {
        "recording_id": recording_id,
        "release_group_id": _optional_text(release_group.get("id")),
        "release_group_primary_type": _optional_text(
            release_group.get("primary-type")
        ),
        "release_group_secondary_types": _optional_text_list(
            release_group.get("secondary-types")
        ),
        "release_status": _optional_text(primary_release.get("status")),
        "title": _optional_text(recording.get("title")),
        "artist": _extract_primary_artist(recording.get("artist-credit")),
        "artist_credit": _flatten_artist_credit(recording.get("artist-credit")),
        "album": _optional_text(primary_release.get("title")),
        "first_release_date": _optional_text(recording.get("first-release-date")),
        "length_ms": _optional_int(recording.get("length")),
        "score": _optional_int(recording.get("score")),
        "disambiguation": _optional_text(recording.get("disambiguation")),
        "musicbrainz_url": f"https://musicbrainz.org/recording/{recording_id}",
    }


def _extract_primary_artist(value: object) -> str | None:
    if not isinstance(value, list) or not value:
        return None
    first = value[0]
    if not isinstance(first, dict):
        return None

    credited_name = _optional_text(first.get("name"))
    if credited_name:
        return credited_name

    artist = first.get("artist")
    if isinstance(artist, dict):
        return _optional_text(artist.get("name"))
    return None


def _flatten_artist_credit(value: object) -> str | None:
    if not isinstance(value, list) or not value:
        return None

    parts: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        credited_name = _optional_text(item.get("name"))
        if not credited_name:
            artist = item.get("artist")
            if isinstance(artist, dict):
                credited_name = _optional_text(artist.get("name"))
        if credited_name:
            parts.append(credited_name)
        join_phrase = _optional_text(item.get("joinphrase"))
        if join_phrase:
            parts.append(join_phrase)

    flattened = "".join(parts).strip()
    return flattened or None


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


def _optional_text_list(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None

    normalized = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return normalized or None
