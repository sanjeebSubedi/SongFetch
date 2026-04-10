from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MetadataSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    recording_id: str = Field(
        min_length=1,
        description="Selected MusicBrainz recording ID for the canonical version",
    )
    release_group_id: str = Field(
        min_length=1,
        description="MusicBrainz release group ID for cover art lookup",
    )
    title: str = Field(min_length=1, description="Selected canonical title")
    artist: str = Field(min_length=1, description="Selected primary artist")
    album: str = Field(min_length=1, description="Selected album name")
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
