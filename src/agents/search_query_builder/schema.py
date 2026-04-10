from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SongRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    song_name: str = Field(description="The title of the song")
    artist: str | None = Field(default=None, description="The name of the artist")
    album: str | None = Field(default=None, description="The album")
    format: Literal["mp3", "m4a"] = Field(
        default="m4a",
        description="The requested audio format",
    )
    search_query: str = Field(description="An optimized YouTube search string")

    @field_validator("artist", "album", mode="before")
    @classmethod
    def empty_string_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value
