from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from queue import Empty, Queue
from threading import Thread
from typing import Any, Generic, Literal, TypeVar, cast

from src.agents.download_selector.schema import DownloadAudioSelection
from src.agents.metadata_request_builder.schema import MetadataLookupRequest
from src.agents.metadata_selector.schema import MetadataSelection
from src.agents.search_query_builder.schema import SongRequest
from src.providers.itunes import ITunesConfig
from src.providers.lrclib import LRCLibConfig
from src.providers.spotify import SpotifyConfig
from src.types import (
    DownloadResult,
    LyricsResult,
    MusicMetadataResult,
    SearchResult,
    TagMetadata,
)

T = TypeVar("T")


@dataclass(slots=True)
class PipelineConfig:
    model: str
    host: str
    temperature: float
    search_limit: int = 5
    metadata_limit: int = 5
    spotify_timeout_seconds: float = 2.0
    refinement_timeout_seconds: float = 4.0
    lyrics_timeout_seconds: float = 4.0
    duration_mismatch_threshold_seconds: int = 20
    max_search_attempts: int = 2


@dataclass(slots=True)
class PipelineDependencies:
    build_song_request: Callable[..., SongRequest]
    search_song_audio: Callable[..., list[SearchResult]]
    build_metadata_lookup_request: Callable[..., MetadataLookupRequest]
    fetch_music_metadata: Callable[..., list[MusicMetadataResult]]
    fetch_spotify_metadata: Callable[..., list[MusicMetadataResult]]
    select_metadata_match: Callable[..., MetadataSelection]
    select_download_audio_request: Callable[..., DownloadAudioSelection]
    select_fallback_download_audio_request: Callable[..., DownloadAudioSelection]
    download_song_audio: Callable[..., DownloadResult]
    fetch_lyrics: Callable[..., LyricsResult | None]
    embed_selected_metadata: Callable[..., dict[str, Any]]
    build_fallback_tag_metadata: Callable[..., TagMetadata]


@dataclass(slots=True)
class PipelineError:
    step: str
    message: str
    recoverable: bool = True


@dataclass(slots=True)
class SearchEvidence:
    quality: Literal["strong", "weak", "uncertain"]
    reasons: list[str] = field(default_factory=list)
    duration_spread_seconds: int | None = None
    closest_duration_gap_seconds: int | None = None
    audio_signal_count: int = 0
    noise_signal_count: int = 0
    provider_duration_agrees: bool | None = None


@dataclass(slots=True)
class RequestState:
    raw_input: str
    request_list: list[SongRequest] = field(default_factory=list)
    current_request: SongRequest | None = None


@dataclass(slots=True)
class SearchState:
    initial_query: str | None = None
    initial_results: list[SearchResult] = field(default_factory=list)
    refined_query: str | None = None
    refined_results: list[SearchResult] = field(default_factory=list)
    attempts: int = 0
    evidence: SearchEvidence | None = None


@dataclass(slots=True)
class MetadataState:
    lookup_request: MetadataLookupRequest | None = None
    itunes_matches: list[MusicMetadataResult] = field(default_factory=list)
    spotify_matches: list[MusicMetadataResult] = field(default_factory=list)
    selected: MetadataSelection | None = None
    source: str | None = None
    fallback_tag_metadata: TagMetadata | None = None


@dataclass(slots=True)
class DownloadState:
    selected: DownloadAudioSelection | None = None
    source: str | None = None
    result: DownloadResult | None = None


@dataclass(slots=True)
class LyricsState:
    result: LyricsResult | None = None
    target: TagMetadata | None = None
    started_early: bool = False
    provisional: bool = False


@dataclass(slots=True)
class TaggingState:
    target: MetadataSelection | TagMetadata | None = None
    result: dict[str, Any] | None = None


@dataclass(slots=True)
class ControlState:
    node: str = "intake"
    status: Literal["running", "completed", "failed"] = "running"
    step_count: int = 0
    max_steps: int = 12
    refinement_budget: int = 2
    final_reason: str | None = None


@dataclass(slots=True)
class PipelineState:
    request: RequestState
    search: SearchState = field(default_factory=SearchState)
    metadata: MetadataState = field(default_factory=MetadataState)
    download: DownloadState = field(default_factory=DownloadState)
    lyrics: LyricsState = field(default_factory=LyricsState)
    tagging: TaggingState = field(default_factory=TaggingState)
    control: ControlState = field(default_factory=ControlState)
    errors: list[PipelineError] = field(default_factory=list)


@dataclass(slots=True)
class BackgroundTask(Generic[T]):
    queue: Queue[tuple[bool, object]]


class SongPipelineController:
    def __init__(
        self,
        *,
        deps: PipelineDependencies,
        config: PipelineConfig,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        self._deps = deps
        self._config = config
        self._progress = progress

    def run(self, user_input: str) -> dict[str, Any]:
        normalized_user_input = user_input.strip()
        if not normalized_user_input:
            raise ValueError("user_input must not be empty")

        request_segments = self._split_request_segments(normalized_user_input)
        if len(request_segments) > 1:
            return self._run_batch(request_segments)

        state = PipelineState(request=RequestState(raw_input=normalized_user_input))

        self._advance(state, "intake")
        self._emit("Parsing request into a song intent")
        song_request = self._deps.build_song_request(
            normalized_user_input,
            model=self._config.model,
            host=self._config.host,
            temperature=self._config.temperature,
        )
        state.request.request_list = [song_request]
        state.request.current_request = song_request

        self._advance(state, "initial_search")
        self._emit("Searching YouTube for grounding evidence")
        initial_results = self._deps.search_song_audio(
            song_request.search_query,
            limit=self._config.search_limit,
        )
        if not initial_results:
            raise RuntimeError(
                "No YouTube search results were found for the generated query."
            )
        state.search.initial_query = song_request.search_query
        state.search.initial_results = initial_results

        self._advance(state, "metadata_lookup_request")
        self._emit("Building canonical metadata lookup request")
        lookup_request = self._deps.build_metadata_lookup_request(
            normalized_user_input,
            initial_results,
            model=self._config.model,
            host=self._config.host,
            temperature=self._config.temperature,
        )
        state.metadata.lookup_request = lookup_request
        state.search.evidence = self._assess_search_evidence(
            initial_results,
            lookup_request=lookup_request,
        )

        lyrics_task: BackgroundTask[LyricsResult | None] | None = None
        provisional_tag_metadata = self._build_provisional_tag_metadata(
            song_request,
            lookup_request,
        )
        if provisional_tag_metadata is not None:
            self._advance(state, "lyrics_lookup")
            self._emit("Starting lyrics lookup early")
            lyrics_task = self._start_background_task(
                self._safe_fetch_lyrics,
                provisional_tag_metadata,
                duration_seconds=None,
                config=LRCLibConfig(),
            )
            state.lyrics.target = provisional_tag_metadata
            state.lyrics.started_early = True
            state.lyrics.provisional = True

        refinement_task: BackgroundTask[list[SearchResult]] | None = None
        if self._should_refine_early(state.search.evidence):
            refinement_task = self._start_background_task(
                self._safe_search_song_audio,
                self._build_refinement_query(
                    song_request,
                    lookup_request,
                    state.search.evidence,
                ),
                self._config.search_limit,
            )
            state.search.refined_query = self._build_refinement_query(
                song_request,
                lookup_request,
                state.search.evidence,
            )
            state.search.attempts = 1

        self._advance(state, "metadata_fetch")
        self._emit("Fetching iTunes metadata first")
        itunes_matches = self._safe_fetch_music_metadata(
            lookup_request.song_name,
            artist=lookup_request.artist,
            limit=self._config.metadata_limit,
            config=ITunesConfig(),
        )
        state.metadata.itunes_matches = itunes_matches

        spotify_matches: list[MusicMetadataResult] = []
        if not itunes_matches or self._should_cross_check_spotify(
            state.search.evidence
        ):
            self._emit("Cross-checking Spotify metadata with a short timeout")
            spotify_task = self._start_background_task(
                self._safe_fetch_spotify_metadata,
                lookup_request.song_name,
                artist=lookup_request.artist,
                limit=self._config.metadata_limit,
                config=SpotifyConfig(),
            )
            spotify_matches, spotify_timed_out = self._await_background_task(
                spotify_task,
                timeout=self._config.spotify_timeout_seconds,
                default=[],
            )
            if spotify_timed_out:
                state.errors.append(
                    PipelineError(
                        step="metadata_fetch",
                        message="Spotify metadata lookup timed out and was treated as best-effort fallback.",
                    )
                )
        state.metadata.spotify_matches = spotify_matches

        metadata_matches = itunes_matches if itunes_matches else spotify_matches
        if metadata_matches:
            self._advance(state, "metadata_selection")
            self._emit("Selecting provider metadata")
            state.metadata.selected = self._deps.select_metadata_match(
                normalized_user_input,
                metadata_matches,
                model=self._config.model,
                host=self._config.host,
                temperature=self._config.temperature,
            )
            state.metadata.source = state.metadata.selected.provider
        else:
            state.metadata.source = "fallback"

        if self._should_refine_after_metadata(
            state.search.initial_results,
            state.metadata.selected,
            state.metadata.itunes_matches,
            state.metadata.spotify_matches,
        ):
            refinement_task = refinement_task or self._start_background_task(
                self._safe_search_song_audio,
                self._build_refinement_query(
                    song_request,
                    lookup_request,
                    state.search.evidence,
                    selected_metadata=state.metadata.selected,
                ),
                self._config.search_limit,
            )
            if state.search.refined_query is None:
                state.search.refined_query = self._build_refinement_query(
                    song_request,
                    lookup_request,
                    state.search.evidence,
                    selected_metadata=state.metadata.selected,
                )
            state.search.attempts = max(state.search.attempts, 1)

        if refinement_task is not None:
            refined_results, _ = self._await_background_task(
                refinement_task,
                timeout=self._config.refinement_timeout_seconds,
                default=[],
            )
            state.search.refined_results = refined_results

        merged_search_results = self._merge_search_results(
            state.search.initial_results,
            state.search.refined_results,
        )
        if not merged_search_results:
            merged_search_results = state.search.initial_results

        selected_download_model: DownloadAudioSelection | None = None
        download_selection_source: str | None = None
        selected_result: SearchResult | None = None
        tag_metadata: TagMetadata | None = None

        if state.metadata.selected is not None:
            self._advance(state, "download_selection")
            self._emit("Selecting best YouTube download candidate")
            try:
                selected_download_model = self._deps.select_download_audio_request(
                    normalized_user_input,
                    state.metadata.selected,
                    merged_search_results,
                    requested_format=song_request.format,
                    model=self._config.model,
                    host=self._config.host,
                    temperature=self._config.temperature,
                )
                download_selection_source = "metadata_selector"
            except Exception as exc:
                state.errors.append(
                    PipelineError(
                        step="download_selection",
                        message=str(exc),
                    )
                )
                selected_download_model = (
                    self._deps.select_fallback_download_audio_request(
                        normalized_user_input,
                        merged_search_results,
                        requested_format=song_request.format,
                        song_name=state.metadata.selected.title,
                        artist=state.metadata.selected.artist,
                    )
                )
                download_selection_source = "fallback_selector"
            tag_metadata = TagMetadata(
                title=state.metadata.selected.title,
                artist=state.metadata.selected.artist,
                album=state.metadata.selected.album,
                genre=state.metadata.selected.genre,
                track_number=state.metadata.selected.track_number,
                disc_number=state.metadata.selected.disc_number,
                artwork_url=state.metadata.selected.artwork_url,
            )
            state.lyrics.provisional = False
            state.tagging.target = state.metadata.selected
        else:
            self._advance(state, "fallback_selection")
            self._emit("Selecting a best-effort fallback candidate")
            selected_download_model = self._deps.select_fallback_download_audio_request(
                normalized_user_input,
                merged_search_results,
                requested_format=song_request.format,
                song_name=lookup_request.song_name,
                artist=lookup_request.artist,
            )
            download_selection_source = "fallback_selector"
            selected_result = self._find_search_result_by_url(
                merged_search_results,
                selected_download_model.tool_call.parameters.url,
            )
            tag_metadata = self._deps.build_fallback_tag_metadata(
                song_request,
                lookup_request,
                selected_result=selected_result,
            )
            state.lyrics.provisional = False
            state.metadata.fallback_tag_metadata = tag_metadata
            state.tagging.target = tag_metadata

        if selected_download_model is None:
            raise RuntimeError("No download candidate could be selected.")

        state.download.selected = selected_download_model
        state.download.source = download_selection_source

        canonical_lyrics_duration_seconds = self._lyrics_duration_seconds(
            selected_metadata=state.metadata.selected,
            search_results=merged_search_results,
            selected_url=selected_download_model.tool_call.parameters.url,
        )
        if tag_metadata is not None and (
            lyrics_task is None
            or not self._tag_metadata_matches(state.lyrics.target, tag_metadata)
        ):
            self._advance(state, "lyrics_lookup")
            self._emit("Refreshing lyrics lookup for canonical metadata")
            lyrics_task = self._start_background_task(
                self._safe_fetch_lyrics,
                tag_metadata,
                duration_seconds=canonical_lyrics_duration_seconds,
                config=LRCLibConfig(),
            )
            state.lyrics.target = tag_metadata

        self._advance(state, "download")
        self._emit("Downloading audio")
        state.download.result = self._deps.download_song_audio(
            selected_download_model.tool_call.parameters.url,
            audio_format=selected_download_model.tool_call.parameters.format,
            filename=selected_download_model.tool_call.parameters.filename,
        )

        if lyrics_task is not None:
            lyrics_result, _ = self._await_background_task(
                lyrics_task,
                timeout=self._config.lyrics_timeout_seconds,
                default=None,
            )
            state.lyrics.result = lyrics_result

        self._advance(state, "tagging")
        self._emit("Embedding artwork, metadata, and lyrics")
        state.tagging.result = self._deps.embed_selected_metadata(
            state.download.result["output_path"],
            state.tagging.target,
            lyrics=(state.lyrics.result.plain_lyrics if state.lyrics.result else None),
        )

        state.control.status = "completed"
        state.control.final_reason = "completed"
        self._advance(state, "finalize")

        return {
            "user_input": normalized_user_input,
            "song_request": song_request.model_dump(),
            "search_results": state.search.initial_results,
            "metadata_lookup_request": lookup_request.model_dump(),
            "metadata_matches": metadata_matches,
            "metadata_source": self._metadata_source(state.metadata.selected),
            "download_selection_source": download_selection_source,
            "selected_metadata": (
                state.metadata.selected.model_dump()
                if state.metadata.selected
                else None
            ),
            "selected_download": state.download.selected.model_dump(),
            "download_result": state.download.result,
            "lyrics_result": self._serialize_lyrics_result(
                state.lyrics.result,
                lyrics_embedded=bool(
                    state.tagging.result.get("lyrics_embedded")
                    if isinstance(state.tagging.result, dict)
                    else False
                ),
            ),
            "tagging_result": state.tagging.result,
        }

    def _split_request_segments(self, user_input: str) -> list[str]:
        segments: list[str] = []
        for raw_segment in user_input.replace("\r\n", "\n").split("\n"):
            for piece in raw_segment.split(";"):
                segment = piece.strip().lstrip("-•*").strip()
                if segment:
                    segments.append(segment)
        if len(segments) > 1:
            return segments
        return [user_input]

    def _run_batch(self, request_segments: list[str]) -> dict[str, Any]:
        results = [self.run(segment) for segment in request_segments]
        return {
            "mode": "batch",
            "user_input": request_segments,
            "requests": [result.get("song_request") for result in results],
            "results": results,
            "summary": self._summarize_batch_results(results),
        }

    def _summarize_batch_results(self, results: list[dict[str, Any]]) -> dict[str, int]:
        summary = {
            "total": len(results),
            "downloaded": 0,
            "metadata_from_itunes": 0,
            "metadata_from_spotify": 0,
            "fallback_only": 0,
            "failed": 0,
        }
        for result in results:
            if not isinstance(result, dict):
                summary["failed"] += 1
                continue
            if result.get("download_result"):
                summary["downloaded"] += 1
            else:
                summary["failed"] += 1

            metadata_source = result.get("metadata_source")
            if metadata_source == "itunes":
                summary["metadata_from_itunes"] += 1
            elif metadata_source == "spotify":
                summary["metadata_from_spotify"] += 1
            else:
                summary["fallback_only"] += 1
        return summary

    def _advance(self, state: PipelineState, node: str) -> None:
        state.control.step_count += 1
        if state.control.step_count > state.control.max_steps:
            state.control.status = "failed"
            raise RuntimeError("Pipeline exceeded its maximum step budget.")
        state.control.node = node

    def _emit(self, message: str) -> None:
        if self._progress is not None:
            self._progress(message)

    def _should_refine_early(self, evidence: SearchEvidence | None) -> bool:
        if evidence is None:
            return False
        if self._config.max_search_attempts <= 1:
            return False
        return evidence.quality != "strong"

    def _should_cross_check_spotify(self, evidence: SearchEvidence | None) -> bool:
        if evidence is None:
            return False
        return evidence.quality != "strong"

    def _should_refine_after_metadata(
        self,
        search_results: list[SearchResult],
        selected_metadata: MetadataSelection | None,
        itunes_matches: list[MusicMetadataResult],
        spotify_matches: list[MusicMetadataResult],
    ) -> bool:
        if selected_metadata is None:
            return False
        if not self._provider_duration_agrees(
            itunes_matches, spotify_matches, selected_metadata
        ):
            return False
        closest_gap = self._closest_duration_gap(
            search_results, selected_metadata.duration_ms
        )
        return (
            closest_gap is not None
            and closest_gap > self._config.duration_mismatch_threshold_seconds
            and self._config.max_search_attempts > 1
        )

    def _assess_search_evidence(
        self,
        search_results: list[SearchResult],
        *,
        lookup_request: MetadataLookupRequest,
    ) -> SearchEvidence:
        reasons: list[str] = []
        audio_signal_count = 0
        noise_signal_count = 0
        durations: list[int] = []
        for result in search_results:
            title = (result.get("title") or "").lower()
            duration = result.get("duration_seconds")
            if (
                isinstance(duration, (int, float))
                and not isinstance(duration, bool)
                and duration > 0
            ):
                durations.append(round(duration))
            if self._is_audio_style_candidate(title):
                audio_signal_count += 1
            if self._is_noise_style_candidate(title):
                noise_signal_count += 1

        duration_spread_seconds = None
        if durations:
            duration_spread_seconds = max(durations) - min(durations)
            if duration_spread_seconds > 45:
                reasons.append("search duration spread is wide")

        if audio_signal_count == 0:
            reasons.append("no audio/topic/lyrics-style candidates near the top")
        if noise_signal_count > audio_signal_count:
            reasons.append("titles are dominated by noisy or disambiguated versions")

        quality: Literal["strong", "weak", "uncertain"]
        if (
            audio_signal_count > 0
            and noise_signal_count == 0
            and (duration_spread_seconds is None or duration_spread_seconds <= 20)
        ):
            quality = "strong"
        elif audio_signal_count == 0 or (
            duration_spread_seconds is not None and duration_spread_seconds > 45
        ):
            quality = "weak"
        else:
            quality = "uncertain"

        if lookup_request.song_name:
            reasons.append(
                f"grounding metadata request centered on {lookup_request.song_name!r}"
            )

        return SearchEvidence(
            quality=quality,
            reasons=reasons,
            duration_spread_seconds=duration_spread_seconds,
            audio_signal_count=audio_signal_count,
            noise_signal_count=noise_signal_count,
        )

    def _build_refinement_query(
        self,
        song_request: SongRequest,
        lookup_request: MetadataLookupRequest,
        evidence: SearchEvidence | None,
        *,
        selected_metadata: MetadataSelection | None = None,
    ) -> str:
        parts: list[str] = []
        if selected_metadata is not None:
            parts.append(selected_metadata.title)
            if selected_metadata.artist:
                parts.append(selected_metadata.artist)
        else:
            parts.append(lookup_request.song_name or song_request.song_name)
            if lookup_request.artist:
                parts.append(lookup_request.artist)

        if evidence is None or evidence.quality != "strong":
            parts.append("official audio lyrics")
        if (
            evidence is not None
            and evidence.noise_signal_count > evidence.audio_signal_count
        ):
            parts.append("topic")

        return self._dedupe_query_terms(parts)

    def _dedupe_query_terms(self, parts: list[str]) -> str:
        terms: list[str] = []
        seen: set[str] = set()
        for part in parts:
            for token in part.split():
                normalized = token.strip()
                if not normalized:
                    continue
                lowered = normalized.lower()
                if lowered in seen:
                    continue
                seen.add(lowered)
                terms.append(normalized)
        return " ".join(terms)

    def _is_audio_style_candidate(self, title: str) -> bool:
        return any(
            token in title
            for token in ("audio", "lyrics", "lyric video", "topic", "official audio")
        )

    def _is_noise_style_candidate(self, title: str) -> bool:
        return any(
            token in title
            for token in (
                "live",
                "cover",
                "remix",
                "reaction",
                "slowed",
                "reverb",
                "karaoke",
                "music video",
                "official video",
                "open session",
                "open sessions",
                "session",
                "performance",
                "acoustic",
                "unplugged",
                "concert",
            )
        )

    def _provider_duration_agrees(
        self,
        itunes_matches: list[MusicMetadataResult],
        spotify_matches: list[MusicMetadataResult],
        selected_metadata: MetadataSelection,
    ) -> bool:
        if selected_metadata.provider == "itunes":
            other_duration = self._first_duration_seconds(spotify_matches)
            local_duration = round(selected_metadata.duration_ms / 1000)
        else:
            other_duration = self._first_duration_seconds(itunes_matches)
            local_duration = round(selected_metadata.duration_ms / 1000)
        if other_duration is None:
            return False
        return abs(local_duration - other_duration) <= 2

    def _first_duration_seconds(self, matches: list[MusicMetadataResult]) -> int | None:
        for match in matches:
            duration_ms = match.get("duration_ms")
            if isinstance(duration_ms, int) and duration_ms > 0:
                return round(duration_ms / 1000)
        return None

    def _closest_duration_gap(
        self,
        search_results: list[SearchResult],
        duration_ms: int,
    ) -> int | None:
        target_seconds = round(duration_ms / 1000)
        gaps: list[int] = []
        for result in search_results:
            duration = result.get("duration_seconds")
            if (
                isinstance(duration, (int, float))
                and not isinstance(duration, bool)
                and duration > 0
            ):
                gaps.append(abs(round(duration) - target_seconds))
        if not gaps:
            return None
        return min(gaps)

    def _merge_search_results(
        self,
        initial_results: list[SearchResult],
        refined_results: list[SearchResult],
    ) -> list[SearchResult]:
        merged: list[SearchResult] = []
        counts: Counter[str] = Counter()
        first_seen: dict[str, SearchResult] = {}
        for result in [*initial_results, *refined_results]:
            key = self._search_result_key(result)
            counts[key] += 1
            if key not in first_seen:
                first_seen[key] = result

        for key, result in first_seen.items():
            enriched = dict(result)
            enriched["search_hit_count"] = counts[key]
            merged.append(enriched)
        return merged

    def _search_result_key(self, result: SearchResult) -> str:
        return (
            result.get("webpage_url") or result.get("id") or result.get("title") or ""
        )

    def _start_background_task(
        self,
        func: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> BackgroundTask[T]:
        result_queue: Queue[tuple[bool, object]] = Queue(maxsize=1)

        def worker() -> None:
            try:
                result_queue.put((True, func(*args, **kwargs)))
            except Exception as exc:  # pragma: no cover - defensive best-effort guard
                result_queue.put((False, exc))

        thread = Thread(target=worker, daemon=True)
        thread.start()
        return BackgroundTask(queue=result_queue)

    def _await_background_task(
        self,
        task: BackgroundTask[T],
        *,
        timeout: float,
        default: T,
    ) -> tuple[T, bool]:
        try:
            success, payload = task.queue.get(timeout=timeout)
        except Empty:
            return default, True
        if success:
            return cast(T, payload), False
        return default, False

    def _safe_search_song_audio(self, query: str, limit: int) -> list[SearchResult]:
        try:
            return self._deps.search_song_audio(query, limit=limit)
        except Exception:
            return []

    def _safe_fetch_music_metadata(
        self,
        song_name: str,
        *,
        artist: str | None,
        limit: int,
        config: ITunesConfig,
    ) -> list[MusicMetadataResult]:
        try:
            return self._deps.fetch_music_metadata(
                song_name,
                artist=artist,
                limit=limit,
                config=config,
            )
        except Exception:
            return []

    def _safe_fetch_spotify_metadata(
        self,
        song_name: str,
        *,
        artist: str | None,
        limit: int,
        config: SpotifyConfig,
    ) -> list[MusicMetadataResult]:
        try:
            return self._deps.fetch_spotify_metadata(
                song_name,
                artist=artist,
                limit=limit,
                config=config,
            )
        except Exception:
            return []

    def _safe_fetch_lyrics(
        self,
        metadata: MetadataSelection | TagMetadata,
        *,
        duration_seconds: int | None,
        config: LRCLibConfig,
    ) -> LyricsResult | None:
        try:
            return self._deps.fetch_lyrics(
                metadata,
                duration_seconds=duration_seconds,
                config=config,
            )
        except Exception:
            return None

    def _lyrics_duration_seconds(
        self,
        *,
        selected_metadata: MetadataSelection | None,
        search_results: list[SearchResult],
        selected_url: str,
    ) -> int | None:
        if selected_metadata is not None:
            return round(selected_metadata.duration_ms / 1000)

        for result in search_results:
            if result.get("webpage_url") != selected_url:
                continue
            duration_seconds = result.get("duration_seconds")
            if (
                isinstance(duration_seconds, (int, float))
                and not isinstance(duration_seconds, bool)
                and duration_seconds > 0
            ):
                return round(duration_seconds)
        return None

    def _find_search_result_by_url(
        self,
        search_results: list[SearchResult],
        url: str,
    ) -> SearchResult | None:
        for result in search_results:
            if result.get("webpage_url") == url:
                return result
        return None

    def _build_provisional_tag_metadata(
        self,
        song_request: SongRequest,
        lookup_request: MetadataLookupRequest,
    ) -> TagMetadata | None:
        title = (
            lookup_request.song_name.strip()
            if lookup_request.song_name.strip()
            else song_request.song_name
        )
        artist = (
            lookup_request.artist.strip()
            if lookup_request.artist.strip()
            else song_request.artist
        )
        if not title:
            return None
        return TagMetadata(
            title=title,
            artist=artist,
            album=song_request.album,
        )

    def _tag_metadata_matches(
        self,
        left: TagMetadata | None,
        right: TagMetadata | None,
    ) -> bool:
        if left is None or right is None:
            return False
        return (
            left.title.strip().lower() == right.title.strip().lower()
            and (left.artist or "").strip().lower()
            == (right.artist or "").strip().lower()
        )

    def _metadata_source(self, selected_metadata: MetadataSelection | None) -> str:
        if selected_metadata is None:
            return "fallback"
        return selected_metadata.provider

    def _serialize_lyrics_result(
        self,
        lyrics_result: LyricsResult | None,
        *,
        lyrics_embedded: bool,
    ) -> dict[str, Any]:
        if lyrics_result is None:
            return {
                "found": False,
                "source": "lrclib",
                "lyrics_embedded": False,
            }
        return {
            "found": lyrics_result.found,
            "source": lyrics_result.source,
            "synced_available": lyrics_result.synced_available,
            "synced_used": lyrics_result.synced_used,
            "lyrics_embedded": lyrics_embedded,
        }
