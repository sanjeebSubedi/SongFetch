"""Shared test fixtures for the audio-agent test suite.

These factory functions return fresh instances of common test objects so that
test cases don't modify each other's state. Import what you need directly:

    from tests.conftest import make_song_request, make_search_results
"""
from __future__ import annotations

from src.agents.download_selector.schema import DownloadAudioSelection
from src.agents.metadata_request_builder.schema import MetadataLookupRequest
from src.agents.metadata_selector.schema import MetadataSelection
from src.agents.search_query_builder.schema import SongRequest
from src.types import DownloadResult, MusicMetadataResult, SearchResult


def make_song_request(
    song_name: str = "Yellow",
    artist: str | None = "Coldplay",
    album: str | None = None,
    fmt: str = "m4a",
    search_query: str = "Coldplay Yellow official audio",
) -> SongRequest:
    return SongRequest(
        song_name=song_name,
        artist=artist,
        album=album,
        format=fmt,
        search_query=search_query,
    )


def make_search_results(
    video_id: str = "abc123",
    title: str = "Coldplay - Yellow",
    uploader: str = "Coldplay",
    duration_seconds: int = 269,
    view_count: int = 42,
) -> list[SearchResult]:
    return [
        {
            "id": video_id,
            "title": title,
            "uploader": uploader,
            "description": None,
            "duration_seconds": duration_seconds,
            "webpage_url": f"https://www.youtube.com/watch?v={video_id}",
            "view_count": view_count,
        }
    ]


def make_metadata_lookup_request(
    song_name: str = "Yellow",
    artist: str | None = "Coldplay",
    reasoning: str = "Coldplay is the clearest consensus across the top YouTube results.",
) -> MetadataLookupRequest:
    return MetadataLookupRequest(
        song_name=song_name,
        artist=artist,
        reasoning=reasoning,
    )


def make_itunes_metadata_matches(
    title: str = "Yellow",
    artist: str = "Coldplay",
    album: str = "Parachutes",
) -> list[MusicMetadataResult]:
    return [
        {
            "provider": "itunes",
            "provider_track_id": "123",
            "provider_collection_id": "456",
            "title": title,
            "artist": artist,
            "album": album,
            "release_date": "2000-06-26T07:00:00Z",
            "duration_ms": 266000,
            "explicitness": "notExplicit",
            "is_explicit": False,
            "track_number": 5,
            "disc_number": 1,
            "genre": "Alternative",
            "artwork_url": "https://example.com/art.jpg",
            "preview_url": "https://example.com/preview.m4a",
            "track_view_url": "https://music.apple.com/us/song/yellow/123",
            "collection_view_url": "https://music.apple.com/us/album/parachutes/456",
        }
    ]


def make_metadata_selection(
    title: str = "Yellow",
    artist: str = "Coldplay",
    album: str = "Parachutes",
) -> MetadataSelection:
    return MetadataSelection(
        provider="itunes",
        provider_track_id="123",
        provider_collection_id="456",
        title=title,
        artist=artist,
        album=album,
        genre="Alternative",
        track_number=5,
        disc_number=1,
        artwork_url="https://example.com/art.jpg",
        duration_ms=266000,
        is_explicit=False,
        reason="Earliest studio album match with valid length.",
    )


def make_download_selection(
    url: str = "https://www.youtube.com/watch?v=abc123",
    fmt: str = "m4a",
    filename: str = "Coldplay - Yellow",
) -> DownloadAudioSelection:
    return DownloadAudioSelection.model_validate(
        {
            "reasoning": "Candidate #1 matches duration and is from an official source.",
            "tool_call": {
                "tool": "download_audio",
                "parameters": {"url": url, "format": fmt, "filename": filename},
            },
        }
    )


def make_download_result(
    video_id: str = "abc123",
    title: str = "Coldplay - Yellow",
    fmt: str = "m4a",
) -> DownloadResult:
    return {
        "id": video_id,
        "title": title,
        "source_url": f"https://www.youtube.com/watch?v={video_id}",
        "output_path": f"downloads/{title}.{fmt}",
        "audio_format": fmt,
    }
