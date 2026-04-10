from __future__ import annotations

from src.agents.metadata_selector.schema import MetadataSelection
from src.providers.lrclib import LRCLibConfig, lookup_lyrics
from src.types import LyricsResult, TagMetadata


def fetch_lyrics(
    metadata: MetadataSelection | TagMetadata,
    *,
    duration_seconds: int | None = None,
    config: LRCLibConfig | None = None,
) -> LyricsResult | None:
    if isinstance(metadata, MetadataSelection):
        if duration_seconds is None and metadata.duration_ms > 0:
            duration_seconds = round(metadata.duration_ms / 1000)

    return lookup_lyrics(
        metadata.title,
        artist=metadata.artist,
        album=metadata.album,
        duration_seconds=duration_seconds,
        config=config,
    )
