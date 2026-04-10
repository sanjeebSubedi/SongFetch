from __future__ import annotations

from typing import TypedDict


class SearchResult(TypedDict):
    id: str | None
    title: str | None
    uploader: str | None
    duration_seconds: int | None
    webpage_url: str | None
    view_count: int | None


class DownloadResult(TypedDict):
    id: str | None
    title: str | None
    source_url: str
    output_path: str
    audio_format: str


class MusicMetadataResult(TypedDict):
    recording_id: str
    release_group_id: str | None
    release_group_primary_type: str | None
    release_group_secondary_types: list[str] | None
    release_status: str | None
    title: str | None
    artist: str | None
    artist_credit: str | None
    album: str | None
    first_release_date: str | None
    length_ms: int | None
    score: int | None
    disambiguation: str | None
    musicbrainz_url: str
