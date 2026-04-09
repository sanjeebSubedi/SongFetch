from __future__ import annotations

import shutil
from pathlib import Path

from audio_agent.tools._shared import (
    DEFAULT_AUDIO_FORMAT,
    DEFAULT_OUTPUT_DIR,
    get_yt_dlp,
    resolve_output_path,
)
from audio_agent.types import DownloadResult


def download_song_audio(
    url: str,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    audio_format: str = DEFAULT_AUDIO_FORMAT,
) -> DownloadResult:
    """Download audio for a selected URL with yt-dlp."""
    source_url = url.strip()
    if not source_url:
        raise ValueError("url must not be empty")

    normalized_format = audio_format.strip().lower()
    if not normalized_format:
        raise ValueError("audio_format must not be empty")

    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    format_selector = "bestaudio/best"
    if normalized_format == "m4a":
        format_selector = "bestaudio[ext=m4a]/bestaudio/best"

    download_options: dict[str, object] = {
        "format": format_selector,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "outtmpl": str(target_dir / "%(title).200B [%(id)s].%(ext)s"),
    }

    if normalized_format != "best":
        if shutil.which("ffmpeg") is None:
            raise RuntimeError(
                f"ffmpeg is required to produce {normalized_format} output."
            )
        download_options["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": normalized_format,
                "preferredquality": "0",
            }
        ]

    yt_dlp = get_yt_dlp()
    with yt_dlp.YoutubeDL(download_options) as ydl:
        info = ydl.extract_info(source_url, download=True)

    output_path = resolve_output_path(info, normalized_format)
    return {
        "id": info.get("id"),
        "title": info.get("title"),
        "source_url": source_url,
        "output_path": str(output_path),
        "audio_format": normalized_format,
    }
