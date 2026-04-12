from __future__ import annotations

import json
import math
import re
from typing import Literal

from src.agents._shared import build_structured_output_prompt
from src.agents.download_selector.prompt import DOWNLOAD_SELECTOR_INSTRUCTIONS
from src.agents.download_selector.schema import (
    DownloadAudioParameters,
    DownloadAudioSelection,
    DownloadAudioToolCall,
)
from src.agents.metadata_selector.schema import MetadataSelection
from src.providers.ollama import (
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_TEMPERATURE,
    OllamaConfig,
    generate_structured_response,
)
from src.types import SearchResult


def select_download_audio_request(
    user_input: str,
    metadata_selection: MetadataSelection,
    search_results: list[SearchResult],
    *,
    requested_format: Literal["mp3", "m4a"],
    model: str = DEFAULT_OLLAMA_MODEL,
    host: str = DEFAULT_OLLAMA_HOST,
    temperature: float = DEFAULT_OLLAMA_TEMPERATURE,
) -> DownloadAudioSelection:
    if not search_results:
        raise ValueError("search_results must not be empty")

    prompt_candidates = _prepare_prompt_candidates(user_input, search_results)

    config = OllamaConfig(
        model=model,
        host=host,
        temperature=temperature,
    )
    return generate_structured_response(
        user_input=_build_user_prompt(
            user_input,
            metadata_selection,
            prompt_candidates,
            requested_format=requested_format,
        ),
        response_model=DownloadAudioSelection,
        system_prompt=_build_system_prompt(),
        config=config,
    )


def select_fallback_download_audio_request(
    user_input: str,
    search_results: list[SearchResult],
    *,
    requested_format: Literal["mp3", "m4a"],
    song_name: str | None = None,
    artist: str | None = None,
) -> DownloadAudioSelection:
    if not search_results:
        raise ValueError("search_results must not be empty")

    best_candidate = _select_best_fallback_candidate(search_results)
    best_title = best_candidate.get("title") or "Unknown Title"
    best_uploader = best_candidate.get("uploader")
    best_url = best_candidate.get("webpage_url")
    if not isinstance(best_url, str) or not best_url.strip():
        raise ValueError("selected fallback candidate did not include a webpage_url")

    filename = _build_fallback_filename(
        song_name=song_name,
        artist=artist,
        candidate_title=best_title,
        candidate_uploader=best_uploader,
    )
    reasoning = _build_fallback_reasoning(
        user_input=user_input,
        candidate=best_candidate,
        all_candidates=search_results,
    )
    return DownloadAudioSelection(
        reasoning=reasoning,
        tool_call=DownloadAudioToolCall(
            tool="download_audio",
            parameters=DownloadAudioParameters(
                url=best_url,
                format=requested_format,
                filename=filename,
            ),
        ),
    )


def _build_system_prompt() -> str:
    return build_structured_output_prompt(
        DOWNLOAD_SELECTOR_INSTRUCTIONS,
        DownloadAudioSelection,
    )


def _prepare_prompt_candidates(
    user_input: str,
    search_results: list[SearchResult],
) -> list[SearchResult]:
    if _user_asked_for_specific_version(user_input):
        return search_results

    audio_or_lyric_candidates = [
        result for result in search_results if _is_audio_or_lyric_candidate(result)
    ]
    if audio_or_lyric_candidates:
        return audio_or_lyric_candidates

    non_session_candidates = [
        result
        for result in search_results
        if not _is_session_or_performance_candidate(result)
    ]
    if non_session_candidates:
        return non_session_candidates

    return search_results


def _select_best_fallback_candidate(
    search_results: list[SearchResult],
) -> SearchResult:
    top_view_count = max((_view_count(result) for result in search_results), default=0)
    return max(
        search_results,
        key=lambda result: (
            _fallback_candidate_score(result, top_view_count=top_view_count),
            _view_count(result),
        ),
    )


def _fallback_candidate_score(
    result: SearchResult,
    *,
    top_view_count: int,
) -> float:
    title = (result.get("title") or "").lower()
    description = (result.get("description") or "").lower()
    uploader = (result.get("uploader") or "").lower()
    score = math.log10(_view_count(result) + 1) * 20

    audio_like = _has_keyword(title, "official audio", " audio", "(audio)", "[audio]")
    lyric_like = _has_keyword(title, "lyrics", "lyric video", "lyric")
    topic_channel = "topic" in uploader
    music_video = _has_keyword(title, "official video", "music video", " mv")
    noisy_variant = _has_keyword(
        title,
        "live",
        "cover",
        "remix",
        "reaction",
        "slowed",
        "reverb",
        "karaoke",
        "open session",
        "open sessions",
        "session",
        "performance",
        "acoustic",
        "unplugged",
        "concert",
    )
    description_noise = _has_keyword(
        description,
        "live",
        "cover",
        "remix",
        "reaction",
        "slowed",
        "reverb",
        "karaoke",
        "open session",
        "open sessions",
        "session",
        "performance",
        "acoustic",
        "unplugged",
        "concert",
    )

    if topic_channel:
        score += 45
    if audio_like:
        score += 40
    if lyric_like:
        score += 25
    if music_video:
        score -= 20
    if noisy_variant:
        score -= 120
    if description_noise:
        score -= 140

    candidate_views = _view_count(result)
    if (topic_channel or audio_like or lyric_like) and candidate_views >= max(
        10_000, int(top_view_count * 0.1)
    ):
        score += 25

    return score


def _view_count(result: SearchResult) -> int:
    view_count = result.get("view_count")
    return view_count if isinstance(view_count, int) and view_count > 0 else 0


def _has_keyword(text: str, *keywords: str) -> bool:
    return any(keyword in text for keyword in keywords)


def _build_fallback_filename(
    *,
    song_name: str | None,
    artist: str | None,
    candidate_title: str | None,
    candidate_uploader: str | None,
) -> str:
    normalized_song_name = _clean_text(song_name)
    normalized_artist = _clean_text(artist)
    if normalized_song_name and normalized_artist:
        return f"{normalized_artist} - {normalized_song_name}"
    if normalized_song_name:
        fallback_artist = _normalize_uploader(candidate_uploader)
        if fallback_artist:
            return f"{fallback_artist} - {normalized_song_name}"
        return normalized_song_name

    cleaned_title = _clean_candidate_title(candidate_title)
    if cleaned_title:
        return cleaned_title
    uploader = _normalize_uploader(candidate_uploader)
    return uploader or "downloaded-audio"


def _build_fallback_reasoning(
    *,
    user_input: str,
    candidate: SearchResult,
    all_candidates: list[SearchResult],
) -> str:
    del user_input
    title = candidate.get("title") or "Unknown title"
    description = (candidate.get("description") or "").lower()
    views = _view_count(candidate)
    top_views = max((_view_count(result) for result in all_candidates), default=0)
    reasons: list[str] = []
    lowered_title = title.lower()
    uploader = candidate.get("uploader") or "unknown uploader"
    if "topic" in uploader.lower():
        reasons.append("topic channel")
    if "audio" in lowered_title:
        reasons.append("audio-focused title")
    if "lyric" in lowered_title:
        reasons.append("lyrics version")
    if any(
        token in description
        for token in (
            "open session",
            "open sessions",
            "performance",
            "live",
            "acoustic",
        )
    ):
        reasons.append("session/performance marker in description")
    if views >= top_views and views > 0:
        reasons.append("highest view count")
    elif views > 0:
        reasons.append(f"strong view count ({views:,})")

    if not reasons:
        reasons.append("best overall fallback score from YouTube results")

    return f'Selected "{title}" from {uploader} based on ' + ", ".join(reasons) + "."


def _user_asked_for_specific_version(user_input: str) -> bool:
    lowered = user_input.lower()
    return any(
        keyword in lowered
        for keyword in (
            "live",
            "acoustic",
            "remix",
            "instrumental",
            "karaoke",
            "sped up",
            "slowed",
            "reverb",
            "open session",
            "open sessions",
            "session",
            "performance",
            "cover",
        )
    )


def _is_audio_or_lyric_candidate(result: SearchResult) -> bool:
    combined = _candidate_text(result)
    return _has_keyword(
        combined,
        "official audio",
        " audio",
        "(audio)",
        "[audio]",
        "lyrics",
        "lyric video",
        "lyric",
        "topic",
    )


def _is_session_or_performance_candidate(result: SearchResult) -> bool:
    combined = _candidate_text(result)
    return _has_keyword(
        combined,
        "live",
        "cover",
        "remix",
        "reaction",
        "slowed",
        "reverb",
        "karaoke",
        "open session",
        "open sessions",
        "session",
        "performance",
        "acoustic",
        "unplugged",
        "concert",
    )


def _candidate_text(result: SearchResult) -> str:
    title = (result.get("title") or "").lower()
    description = (result.get("description") or "").lower()
    uploader = (result.get("uploader") or "").lower()
    return f"{title} {description} {uploader}"


def _clean_text(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_uploader(value: str | None) -> str | None:
    normalized = _clean_text(value)
    if not normalized:
        return None
    normalized = re.sub(r"\s*-\s*topic$", "", normalized, flags=re.IGNORECASE)
    return normalized.strip() or None


def _clean_candidate_title(title: str | None) -> str | None:
    normalized = _clean_text(title)
    if not normalized:
        return None
    normalized = re.sub(r"\[[^\]]+\]|\([^)]+\)", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip(" -")
    return normalized or None


def _build_user_prompt(
    user_input: str,
    metadata_selection: MetadataSelection,
    search_results: list[SearchResult],
    *,
    requested_format: Literal["mp3", "m4a"],
) -> str:
    reference_metadata = metadata_selection.model_dump()
    reference_duration_ms = metadata_selection.duration_ms
    # Normalize to the same unit as YouTube candidates for consistent comparisons.
    reference_metadata["duration_seconds"] = round(reference_duration_ms / 1000)
    reference_metadata.pop("duration_ms", None)

    payload = {
        "original_user_request": user_input.strip(),
        "requested_format": requested_format,
        "reference_metadata": reference_metadata,
        "youtube_candidates": [
            {
                "rank": index,
                "id": result.get("id"),
                "title": result.get("title"),
                "uploader": result.get("uploader"),
                "description": result.get("description"),
                "duration_seconds": result.get("duration_seconds"),
                "duration_delta_seconds": _duration_delta_seconds(
                    reference_duration_seconds=reference_duration_ms / 1000,
                    candidate_duration_seconds=result.get("duration_seconds"),
                ),
                "search_hit_count": result.get("search_hit_count") or 1,
                "view_count": result.get("view_count"),
                "webpage_url": result.get("webpage_url"),
                "signals": _candidate_signals(result),
            }
            for index, result in enumerate(search_results, start=1)
        ],
    }
    return json.dumps(payload, indent=2)


def _duration_delta_seconds(
    *,
    reference_duration_seconds: float,
    candidate_duration_seconds: object,
) -> int | None:
    if not isinstance(candidate_duration_seconds, (int, float)) or isinstance(
        candidate_duration_seconds, bool
    ):
        return None
    if candidate_duration_seconds <= 0:
        return None
    return round(candidate_duration_seconds - reference_duration_seconds)


def _candidate_signals(result: SearchResult) -> dict[str, bool]:
    title = (result.get("title") or "").lower()
    description = (result.get("description") or "").lower()
    uploader = (result.get("uploader") or "").lower()
    combined = f"{title} {description}"

    return {
        "audio_like": _has_keyword(
            combined, "official audio", " audio", "(audio)", "[audio]"
        ),
        "lyrics_like": _has_keyword(combined, "lyrics", "lyric video", "lyric"),
        "topic_channel": "topic" in uploader,
        "music_video": _has_keyword(combined, "official video", "music video", " mv"),
        "session_like": _has_keyword(
            combined,
            "live",
            "cover",
            "remix",
            "reaction",
            "slowed",
            "reverb",
            "karaoke",
            "open session",
            "open sessions",
            "session",
            "performance",
            "acoustic",
            "unplugged",
            "concert",
        ),
    }
