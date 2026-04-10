from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import yt_dlp
except ImportError:  # pragma: no cover - depends on the runtime environment
    yt_dlp = None

DEFAULT_OUTPUT_DIR = Path("downloads")
DEFAULT_AUDIO_FORMAT = "m4a"


def get_yt_dlp():
    if yt_dlp is None:
        raise RuntimeError(
            "yt-dlp is not installed. Install dependencies first with `pip install -e .`."
        )
    return yt_dlp


def resolve_output_path(info: dict[str, Any], audio_format: str) -> Path:
    filepath = info.get("filepath") or info.get("_filename")
    requested_downloads = info.get("requested_downloads")

    if not filepath and isinstance(requested_downloads, list):
        for item in requested_downloads:
            if isinstance(item, dict) and item.get("filepath"):
                filepath = item["filepath"]
                break

    if not filepath:
        raise RuntimeError("yt-dlp completed, but no output path was returned.")

    output_path = Path(filepath)
    if audio_format != "best":
        output_path = output_path.with_suffix(f".{audio_format}")
    return output_path
