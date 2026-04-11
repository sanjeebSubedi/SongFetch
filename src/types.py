from __future__ import annotations

from dataclasses import dataclass
from typing import NotRequired, TypedDict


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
    skipped: NotRequired[bool]


class MusicMetadataResult(TypedDict):
    provider: str
    provider_track_id: str
    provider_collection_id: str | None
    title: str | None
    artist: str | None
    album: str | None
    release_date: str | None
    duration_ms: int | None
    explicitness: str | None
    is_explicit: bool | None
    track_number: int | None
    disc_number: int | None
    genre: str | None
    artwork_url: str | None
    preview_url: str | None
    track_view_url: str | None
    collection_view_url: str | None


@dataclass(frozen=True, slots=True)
class TagMetadata:
    title: str
    artist: str | None = None
    album: str | None = None
    genre: str | None = None
    track_number: int | None = None
    disc_number: int | None = None
    artwork_url: str | None = None


@dataclass(frozen=True, slots=True)
class LyricsResult:
    plain_lyrics: str
    source: str
    found: bool = True
    synced_available: bool = False
    synced_used: bool = False


@dataclass(frozen=True, slots=True)
class PlaylistTrack:
    provider: str
    provider_track_id: str
    title: str
    artist: str
    album: str | None = None
    artwork_url: str | None = None
    spotify_track_url: str | None = None
