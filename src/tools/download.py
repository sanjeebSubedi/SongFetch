from __future__ import annotations

import re
import shutil
from pathlib import Path

from src.tools._shared import (
    DEFAULT_AUDIO_FORMAT,
    build_cookies_from_browser,
    build_yt_dlp_runtime_options,
    DEFAULT_OUTPUT_DIR,
    get_yt_dlp,
    resolve_output_path,
)
from src.types import DownloadResult


def download_song_audio(
    url: str,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    audio_format: str = DEFAULT_AUDIO_FORMAT,
    filename: str | None = None,
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

    # Always fetch the best available source audio and let ffmpeg produce the
    # requested output format. This avoids failing on videos that do not expose
    # a native m4a stream while still preserving best-effort quality.
    format_selector = "bestaudio/best"

    output_template = "%(title).200B [%(id)s].%(ext)s"
    if filename is not None:
        output_template = f"{_sanitize_filename_stem(filename)}.%(ext)s"

    download_options: dict[str, object] = {
        "format": format_selector,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "outtmpl": str(target_dir / output_template),
    }
    cookies_from_browser = build_cookies_from_browser()
    if cookies_from_browser is not None:
        download_options["cookiesfrombrowser"] = cookies_from_browser
    download_options.update(build_yt_dlp_runtime_options())

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
        info = ydl.extract_info(source_url, download=False)
        if info is None:
            raise RuntimeError(
                f"yt-dlp could not extract info for the given URL: {source_url}"
            )
        planned_output_path = _predict_output_path(
            ydl,
            info,
            target_dir=target_dir,
            audio_format=normalized_format,
            filename=filename,
        )
        if planned_output_path.exists():
            return {
                "id": info.get("id"),
                "title": info.get("title"),
                "source_url": source_url,
                "output_path": str(planned_output_path),
                "audio_format": normalized_format,
                "skipped": True,
            }

        if hasattr(ydl, "process_ie_result"):
            info = ydl.process_ie_result(info, download=True)
        else:
            info = ydl.extract_info(source_url, download=True)

    output_path = resolve_output_path(info, normalized_format)
    return {
        "id": info.get("id"),
        "title": info.get("title"),
        "source_url": source_url,
        "output_path": str(output_path),
        "audio_format": normalized_format,
    }


def _predict_output_path(
    ydl: object,
    info: dict[str, object],
    *,
    target_dir: Path,
    audio_format: str,
    filename: str | None,
) -> Path:
    if filename is not None:
        stem = _sanitize_filename_stem(filename)
        if audio_format == "best":
            extension = str(info.get("ext") or "webm")
        else:
            extension = audio_format
        return target_dir / f"{stem}.{extension}"

    if hasattr(ydl, "prepare_filename"):
        candidate_path = ydl.prepare_filename(info)
        if candidate_path:
            output_path = Path(candidate_path)
            if audio_format != "best":
                output_path = output_path.with_suffix(f".{audio_format}")
            return output_path

    return resolve_output_path(info, audio_format)


def _sanitize_filename_stem(raw_filename: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", raw_filename)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().strip(".")
    if not cleaned:
        raise ValueError("filename must contain at least one valid character")
    return cleaned[:200]
