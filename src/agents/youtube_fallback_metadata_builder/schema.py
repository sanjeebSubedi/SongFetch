from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class YouTubeFallbackMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(
        min_length=1,
        description="Best-effort canonical song title inferred from YouTube title and description",
    )
    artist: str | None = Field(
        default=None,
        description="Best-effort primary artist inferred from YouTube title and description",
    )
    album: str | None = Field(
        default=None,
        description="Best-effort album inferred from the YouTube description when available",
    )
    artwork_url: str | None = Field(
        default=None,
        description=(
            "Artwork URL to embed. Use the provided YouTube thumbnail URL when no better "
            "artwork can be inferred."
        ),
    )
    confidence: Literal["low", "medium", "high"] = Field(
        description="How confident the fallback inference is",
    )
    reasoning: str = Field(
        min_length=1,
        description="Short explanation for the fallback metadata choice",
    )
