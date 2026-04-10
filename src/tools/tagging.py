from __future__ import annotations

from pathlib import Path
from typing import Any

from src.agents.metadata_selector.schema import MetadataSelection


def embed_selected_metadata(
    file_path: str | Path,
    metadata_selection: MetadataSelection,
) -> dict[str, str]:
    path = Path(file_path)
    extension = path.suffix.lower()
    if not extension:
        raise ValueError("file_path must include a file extension")

    if extension in {".m4a", ".mp4", ".m4b"}:
        _tag_mp4(path, metadata_selection)
    elif extension == ".mp3":
        _tag_mp3(path, metadata_selection)
    else:
        raise ValueError(f"Unsupported audio extension for metadata tagging: {extension}")

    return {
        "path": str(path),
        "container": extension.lstrip("."),
    }


def _tag_mp4(path: Path, metadata_selection: MetadataSelection) -> None:
    MP4 = _load_mutagen_mp4()
    audio = MP4(path)
    if audio.tags is None:
        audio.add_tags()

    tags = audio.tags
    tags["\xa9nam"] = [metadata_selection.title]
    tags["\xa9ART"] = [metadata_selection.artist]
    tags["\xa9alb"] = [metadata_selection.album]
    audio.save()


def _tag_mp3(path: Path, metadata_selection: MetadataSelection) -> None:
    EasyID3, ID3NoHeaderError = _load_mutagen_easyid3()
    try:
        audio = EasyID3(path)
    except ID3NoHeaderError:
        audio = EasyID3()
        audio.save(path)
        audio = EasyID3(path)

    audio["title"] = metadata_selection.title
    audio["artist"] = metadata_selection.artist
    audio["album"] = metadata_selection.album
    audio.save()


def _load_mutagen_mp4():
    try:
        from mutagen.mp4 import MP4
    except ImportError as exc:  # pragma: no cover - depends on runtime dependencies
        raise RuntimeError(
            "mutagen is not installed. Install dependencies first with `pip install -e .`."
        ) from exc
    return MP4


def _load_mutagen_easyid3() -> tuple[Any, Any]:
    try:
        from mutagen.easyid3 import EasyID3
        from mutagen.id3 import ID3NoHeaderError
    except ImportError as exc:  # pragma: no cover - depends on runtime dependencies
        raise RuntimeError(
            "mutagen is not installed. Install dependencies first with `pip install -e .`."
        ) from exc
    return EasyID3, ID3NoHeaderError
