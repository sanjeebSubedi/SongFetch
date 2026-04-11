from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MetadataSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    provider: Literal["itunes", "spotify"] = Field(
        description="Metadata provider selected as the source of truth",
    )
    provider_track_id: str = Field(
        min_length=1,
        description="Provider-specific track identifier for the selected version",
    )
    provider_collection_id: str | None = Field(
        default=None,
        description="Provider-specific album or collection identifier when available",
    )
    title: str = Field(min_length=1, description="Selected canonical title")
    artist: str = Field(min_length=1, description="Selected primary artist")
    album: str = Field(min_length=1, description="Selected album name")
    genre: str | None = Field(
        default=None,
        description="Selected genre when available from the provider metadata",
    )
    track_number: int | None = Field(
        default=None,
        gt=0,
        description="Track number from the selected album/collection when available",
    )
    disc_number: int | None = Field(
        default=None,
        gt=0,
        description="Disc number from the selected album/collection when available",
    )
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
