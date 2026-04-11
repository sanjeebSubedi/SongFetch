from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib import error, request

from src.agents.metadata_selector.schema import MetadataSelection
from src.types import TagMetadata

_ITUNES_ARTWORK_SIZES = (
    "3000x3000bb",
    "2000x2000bb",
    "1400x1400bb",
    "1200x1200bb",
    "600x600bb",
)


def embed_selected_metadata(
    file_path: str | Path,
    metadata_selection: MetadataSelection | TagMetadata,
    *,
    lyrics: str | None = None,
) -> dict[str, str | bool]:
    path = Path(file_path)
    extension = path.suffix.lower()
    if not extension:
        raise ValueError("file_path must include a file extension")

    artwork = _fetch_cover_art(getattr(metadata_selection, "artwork_url", None))
    normalized_lyrics = _normalize_lyrics(lyrics)

    if extension in {".m4a", ".mp4", ".m4b"}:
        _tag_mp4(path, metadata_selection, artwork, normalized_lyrics)
    elif extension == ".mp3":
        _tag_mp3(path, metadata_selection, artwork, normalized_lyrics)
    else:
        raise ValueError(f"Unsupported audio extension for metadata tagging: {extension}")

    return {
        "path": str(path),
        "container": extension.lstrip("."),
        "artwork_embedded": artwork is not None,
        "lyrics_embedded": normalized_lyrics is not None,
    }


def _tag_mp4(
    path: Path,
    metadata_selection: MetadataSelection | TagMetadata,
    artwork: tuple[bytes, str] | None,
    lyrics: str | None,
) -> None:
    MP4, MP4Cover = _load_mutagen_mp4()
    audio = MP4(path)
    if audio.tags is None:
        audio.add_tags()

    tags = audio.tags
    tags["\xa9nam"] = [metadata_selection.title]
    if metadata_selection.artist:
        tags["\xa9ART"] = [metadata_selection.artist]
    if metadata_selection.album:
        tags["\xa9alb"] = [metadata_selection.album]
    if getattr(metadata_selection, "genre", None):
        tags["\xa9gen"] = [metadata_selection.genre]
    if getattr(metadata_selection, "track_number", None):
        tags["trkn"] = [(metadata_selection.track_number, 0)]
    if getattr(metadata_selection, "disc_number", None):
        tags["disk"] = [(metadata_selection.disc_number, 0)]
    if lyrics:
        tags["\xa9lyr"] = [lyrics]
    if artwork is not None:
        image_data, mime_type = artwork
        image_format = (
            MP4Cover.FORMAT_PNG if mime_type == "image/png" else MP4Cover.FORMAT_JPEG
        )
        tags["covr"] = [MP4Cover(image_data, imageformat=image_format)]
    audio.save()


def _tag_mp3(
    path: Path,
    metadata_selection: MetadataSelection | TagMetadata,
    artwork: tuple[bytes, str] | None,
    lyrics: str | None,
) -> None:
    EasyID3, ID3NoHeaderError = _load_mutagen_easyid3()
    try:
        audio = EasyID3(path)
    except ID3NoHeaderError:
        audio = EasyID3()
        audio.save(path)
        audio = EasyID3(path)

    audio["title"] = metadata_selection.title
    if metadata_selection.artist:
        audio["artist"] = metadata_selection.artist
    if metadata_selection.album:
        audio["album"] = metadata_selection.album
    if getattr(metadata_selection, "genre", None):
        audio["genre"] = metadata_selection.genre
    if getattr(metadata_selection, "track_number", None):
        audio["tracknumber"] = str(metadata_selection.track_number)
    if getattr(metadata_selection, "disc_number", None):
        audio["discnumber"] = str(metadata_selection.disc_number)
    audio.save()

    if artwork is not None or lyrics:
        ID3, APIC, USLT = _load_mutagen_id3()
        id3_tags = ID3(path)
    else:
        return

    if artwork is not None:
        image_data, mime_type = artwork
        id3_tags.delall("APIC")
        id3_tags.add(
            APIC(
                encoding=3,
                mime=mime_type,
                type=3,
                desc="Cover",
                data=image_data,
            )
        )
    if lyrics:
        id3_tags.delall("USLT")
        id3_tags.add(
            USLT(
                encoding=3,
                lang="eng",
                desc="Lyrics",
                text=lyrics,
            )
        )
    id3_tags.save()


def _load_mutagen_mp4():
    try:
        from mutagen.mp4 import MP4, MP4Cover
    except ImportError as exc:  # pragma: no cover - depends on runtime dependencies
        raise RuntimeError(
            "mutagen is not installed. Install dependencies first with `pip install -e .`."
        ) from exc
    return MP4, MP4Cover


def _load_mutagen_easyid3() -> tuple[Any, Any]:
    try:
        from mutagen.easyid3 import EasyID3
        from mutagen.id3 import ID3NoHeaderError
    except ImportError as exc:  # pragma: no cover - depends on runtime dependencies
        raise RuntimeError(
            "mutagen is not installed. Install dependencies first with `pip install -e .`."
        ) from exc
    return EasyID3, ID3NoHeaderError


def _load_mutagen_id3() -> tuple[Any, Any]:
    try:
        from mutagen.id3 import APIC, ID3, USLT
    except ImportError as exc:  # pragma: no cover - depends on runtime dependencies
        raise RuntimeError(
            "mutagen is not installed. Install dependencies first with `pip install -e .`."
        ) from exc
    return ID3, APIC, USLT


def _normalize_lyrics(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _fetch_cover_art(artwork_url: str | None) -> tuple[bytes, str] | None:
    if not artwork_url:
        return None

    for candidate_url in _artwork_candidate_urls(artwork_url):
        raw_request = request.Request(
            candidate_url,
            headers={"Accept": "image/*"},
            method="GET",
        )
        try:
            with request.urlopen(raw_request, timeout=10) as response:
                image_data = response.read()
                if not image_data:
                    continue
                mime_type = _detect_mime_type(
                    image_data,
                    content_type=_response_content_type(response),
                    source_url=candidate_url,
                )
                return image_data, mime_type
        except (error.HTTPError, error.URLError):
            continue

    return None


def _artwork_candidate_urls(artwork_url: str) -> list[str]:
    candidates: list[str] = []
    match = re.search(
        r"/(?P<size>\d+x\d+[a-z0-9-]*)\.(?P<ext>jpe?g|png)(?P<suffix>\?.*)?$",
        artwork_url,
        flags=re.IGNORECASE,
    )
    if not match:
        return [artwork_url]

    for size in _ITUNES_ARTWORK_SIZES:
        candidate = artwork_url.replace(match.group("size"), size, 1)
        if candidate not in candidates:
            candidates.append(candidate)
    if artwork_url not in candidates:
        candidates.append(artwork_url)
    return candidates


def _response_content_type(response: Any) -> str | None:
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    get_content_type = getattr(headers, "get_content_type", None)
    if callable(get_content_type):
        return get_content_type()
    if hasattr(headers, "get"):
        value = headers.get("Content-Type")
        if isinstance(value, str):
            return value.split(";", maxsplit=1)[0].strip().lower()
    return None


def _detect_mime_type(
    image_data: bytes,
    *,
    content_type: str | None,
    source_url: str,
) -> str:
    if content_type in {"image/jpeg", "image/png"}:
        return content_type

    if image_data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"

    if source_url.lower().endswith(".png"):
        return "image/png"
    return "image/jpeg"
