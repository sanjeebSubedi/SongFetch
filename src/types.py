from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict


class SearchResult(TypedDict):
    id: str | None
    title: str | None
    uploader: str | None
    description: str | None
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
    track_id: int
    collection_id: int | None
    title: str | None
    artist: str | None
    album: str | None
    release_date: str | None
    duration_ms: int | None
    track_explicitness: str | None
    is_explicit: bool | None
    track_number: int | None
    disc_number: int | None
    primary_genre_name: str | None
    artwork_url: str | None
    preview_url: str | None
    track_view_url: str | None
    collection_view_url: str | None


@dataclass(frozen=True, slots=True)
class TagMetadata:
    title: str
    artist: str | None = None
    album: str | None = None
    artwork_url: str | None = None


@dataclass(frozen=True, slots=True)
class LyricsResult:
    plain_lyrics: str
    source: str
    found: bool = True
    synced_available: bool = False
    synced_used: bool = False
