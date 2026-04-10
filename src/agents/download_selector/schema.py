from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DownloadAudioParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    url: str = Field(min_length=1, description="Selected YouTube URL to download")
    format: Literal["mp3", "m4a"] = Field(
        description="Requested output audio format"
    )
    filename: str = Field(
        min_length=1,
        description="Clean filename stem, e.g. 'Artist - Song Title'",
    )


class DownloadAudioToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    tool: Literal["download_audio"] = Field(
        description="Tool identifier for downloading the selected audio"
    )
    parameters: DownloadAudioParameters


class DownloadAudioSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reasoning: str = Field(
        min_length=1,
        description="Brief explanation covering duration match and source decision",
    )
    tool_call: DownloadAudioToolCall
