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
