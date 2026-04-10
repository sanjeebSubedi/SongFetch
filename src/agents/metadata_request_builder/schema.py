from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MetadataLookupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    song_name: str = Field(
        min_length=1,
        description="Canonical song title to use for the metadata lookup",
    )
    artist: str = Field(
        min_length=1,
        description="Primary artist name to use for the metadata lookup",
    )
    reasoning: str = Field(
        min_length=1,
        description=(
            "Brief explanation for why this song and artist were chosen based on the "
            "YouTube titles, uploaders, and view counts"
        ),
    )
