from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MetadataSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    track_id: int = Field(
        gt=0,
        description="Selected iTunes track ID for the canonical version",
    )
    collection_id: int = Field(
        gt=0,
        description="Selected iTunes collection ID for future artwork or album lookups",
    )
    title: str = Field(min_length=1, description="Selected canonical title")
    artist: str = Field(min_length=1, description="Selected primary artist")
    album: str = Field(min_length=1, description="Selected album name")
    artwork_url: str | None = Field(
        default=None,
        description="Artwork URL for the selected track, if available",
    )
    duration_ms: int = Field(
        gt=0,
        description="Selected canonical track duration in milliseconds",
    )
    is_explicit: bool = Field(
        description="Whether the selected version is explicit content",
    )
    reason: str = Field(
        min_length=1,
        description="Brief explanation for why this candidate was selected",
    )
