from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

try:
    import yt_dlp
except ImportError:  # pragma: no cover - depends on the runtime environment
    yt_dlp = None

DEFAULT_OUTPUT_DIR = Path("downloads")
DEFAULT_AUDIO_FORMAT = "m4a"
DEFAULT_COOKIES_BROWSER = os.environ.get("YTDLP_COOKIES_BROWSER", "firefox").strip()
DEFAULT_COOKIES_PROFILE = os.environ.get("YTDLP_COOKIES_PROFILE", "").strip() or None
DEFAULT_JS_RUNTIME = os.environ.get("YTDLP_JS_RUNTIME", "node").strip().lower()
DEFAULT_REMOTE_COMPONENTS = tuple(
    component.strip()
    for component in os.environ.get("YTDLP_REMOTE_COMPONENTS", "ejs:github").split(",")
    if component.strip()
)


def build_cookies_from_browser() -> tuple[str, ...] | None:
    normalized_browser = DEFAULT_COOKIES_BROWSER.strip().lower()
    if not normalized_browser or normalized_browser in {"none", "off", "false"}:
        return None
    if DEFAULT_COOKIES_PROFILE:
        return (normalized_browser, DEFAULT_COOKIES_PROFILE)
    return (normalized_browser,)


def build_yt_dlp_runtime_options() -> dict[str, object]:
    normalized_runtime = DEFAULT_JS_RUNTIME.strip().lower()
    if not normalized_runtime or normalized_runtime in {"none", "off", "false"}:
        return {}

    runtime_path = shutil.which(normalized_runtime)
    if runtime_path is None:
        return {}

    options: dict[str, object] = {"js_runtimes": {normalized_runtime: {}}}
    if DEFAULT_REMOTE_COMPONENTS:
        options["remote_components"] = list(DEFAULT_REMOTE_COMPONENTS)
    return options


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
