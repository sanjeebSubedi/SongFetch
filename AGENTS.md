# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Also install `ffmpeg` system-wide for audio format conversion.

### Run the pipeline

```bash
.venv/bin/python main.py "download Yellow by Coldplay as m4a" --search-limit 5 --metadata-limit 5
```

### Run a Spotify playlist

```bash
.venv/bin/python main.py --spotify-playlist "https://open.spotify.com/playlist/PLAYLIST_ID"
```

### Run tests

```bash
.venv/bin/python -m pytest tests/
```

### Run a single test file

```bash
.venv/bin/python -m pytest tests/test_main.py
```

### Run a single test case

```bash
.venv/bin/python -m pytest tests/test_main.py::MainTests::test_run_pipeline_returns_staged_payload
```

## Architecture

The main orchestration lives in `src/pipeline.py:SongPipelineController`. `main.py:run_pipeline()` now builds the dependency/config bundle and delegates to the controller, which maintains a shared `PipelineState` for each run.

Current control flow:

1. **Intake / parse** — `build_song_request` parses the user input into a `SongRequest`.
2. **Grounding search** — `search_song_audio` performs the first YouTube search and is treated as evidence, even for misspellings or lyric-like user input.
3. **Metadata request building** — `build_metadata_lookup_request` canonicalizes the song title/artist from the YouTube evidence.
4. **Metadata fetch** — iTunes is tried first; Spotify is used only as a short-timeout fallback or duration cross-check when needed.
5. **Evidence refinement** — weak search evidence can trigger a parallel refinement YouTube search with `lyrics`/`official audio` style terms.
6. **Candidate merge/decision** — initial and refined search pools are merged before download selection.
7. **Download selection** — `select_download_audio_request` is used when metadata is available; `select_fallback_download_audio_request` handles the best-effort path.
8. **Download** — `download_song_audio` downloads and converts the chosen audio.
9. **Lyrics lookup** — `fetch_lyrics` can start early from provisional metadata and is refreshed if canonical metadata changes.
10. **Tagging** — `embed_selected_metadata` writes audio tags, artwork, and lyrics.

Batch and playlist handling:

- Multi-song user input is split into a batch when it contains separate requests on newlines or semicolons.
- `run_spotify_playlist_pipeline()` converts playlist tracks into per-track user requests and runs the same controller per song.

### Key structural patterns

**Agents** (`src/agents/<name>/`) — Each agent is a triplet of `agent.py` (function), `prompt.py` (system prompt text), and `schema.py` (Pydantic output model). All agents call `generate_structured_response()` from `src/providers/ollama.py`, which handles JSON extraction and validation retries.

**Tools** (`src/tools/`) — Pure functions that call external services (yt-dlp, iTunes API, LRCLIB, mutagen). Tools do not call agents.

**Providers** (`src/providers/`) — Thin clients and config dataclasses for each external service (Ollama, iTunes, Spotify, LRCLIB).

**Types** (`src/types.py`) — Shared `TypedDict` and `dataclass` types: `SearchResult`, `DownloadResult`, `MusicMetadataResult`, `TagMetadata`, `LyricsResult`, `PlaylistTrack`.

**Public exports** (`src/__init__.py`) — Re-exports the main entry-point functions and Pydantic schemas for external use.

### LLM integration

All LLM calls go through `src/providers/ollama.py:generate_structured_response()`, which uses Ollama's structured output mode (`format=response_model.model_json_schema()`). The system prompt is built by `src/agents/_shared.py:build_structured_output_prompt()`, which appends the JSON schema to the instruction text. Default model is `gemma4:31b-cloud` at temperature 0.

### Metadata fallback chain

iTunes → Spotify (scraper-based, via `spotify_scraper`) → fallback `TagMetadata` derived from the YouTube result title/description, with the YouTube thumbnail used as the last-resort artwork source. The `metadata_source` field in the pipeline output reflects which provider succeeded (`"itunes"`, `"spotify"`, or `"fallback"`).

## Environment variables

Copy `.env.example` to `.env`. Key variables:

- `SPOTIFY_BROWSER_TYPE`, `SPOTIFY_HEADLESS` — controls the Selenium browser used for Spotify scraping
- `YTDLP_COOKIES_BROWSER` / `YTDLP_COOKIES_PROFILE` — browser cookies for authenticated YouTube access
- `YTDLP_REMOTE_COMPONENTS` — JS runtime for YouTube challenge solving (default: `ejs:github`)
- `ITUNES_COUNTRY` — overrides the iTunes storefront country (also exposed as `--itunes-country` CLI flag)

## Transition Sketch

Current behavior is a state-driven pipeline with bounded refinement loops. The controller keeps one shared `PipelineState` per song, can batch multiple songs, and will continue on partial failure when a best-effort result is still possible.

### Core State

The transition model should carry a shared `PipelineState` for one or more songs:

- `request_list` — normalized song intents for single songs, multi-song requests, or playlist tracks
- `current_request` — active song intent being processed
- `search` — initial query, refined queries, candidate pools, and evidence confidence
- `metadata` — iTunes results, Spotify results, selected metadata, source, timeout flags
- `download` — selected YouTube candidate, fallback usage, and download result
- `lyrics` — lookup target, lookup result, early-start flag, and embed status
- `tagging` — final metadata payload and tagging result
- `control` — node name, retry counters, max steps, and terminal status
- `errors` — recoverable and terminal failures

### Node Flow

```text
Intake
  -> Normalize Request
  -> Initial YouTube Search
  -> Metadata Fetch
       -> iTunes first
       -> Spotify in short-timeout fallback / cross-check branch
  -> Early Lyrics Probe
  -> Parallel Refinement Search
       -> append lyrics/audio terms when evidence is weak
  -> Merge Candidate Pools
  -> Candidate Decision
       -> evidence review and download selection merged here
  -> Download
  -> Lyrics Lookup / Refresh
  -> Tagging
  -> Finalize
```

### Transition Conditions

- `Intake -> Normalize Request` when the raw user input has been parsed into one or more song intents.
- `Normalize Request -> Initial YouTube Search` when the request has a song title and enough context to search.
- `Initial YouTube Search -> Metadata Fetch` immediately after the first result set is available; the first search is used as grounding evidence even when the user typed misspellings or lyrics instead of the canonical title.
- `Initial YouTube Search -> Early Lyrics Probe` when a provisional title/artist is available and lyrics can be fetched in parallel.
- `Initial YouTube Search -> Parallel Refinement Search` when the search evidence is weak or uncertain.
- `Weak search` means one or more of the following is true:
  - no audio/topic/lyrics-style candidates appear near the top
  - titles are noisy or heavily disambiguated
  - title/artist consensus is inconsistent across top results
  - duration spread is large relative to the target song
  - YouTube results and metadata disagree materially on the canonical song
- `Metadata Fetch -> Candidate Decision` once iTunes has returned usable results, or Spotify returns after its short timeout, or both are empty.
- `Metadata Fetch -> Fallback Tag Metadata` only when both provider branches fail to produce usable metadata.
- `Parallel Refinement Search -> Merge Candidate Pools` after the refined YouTube query returns results.
- `Merge Candidate Pools -> Candidate Decision` after combining the grounding search and refinement search candidates.
- `Candidate Decision -> Search Refinement` only when metadata confidence is high enough to reject the current YouTube pool and the refinement budget has not been exhausted.
- `Candidate Decision -> Download` when a candidate matches the selected metadata closely enough or the best-effort fallback selector has chosen a reasonable audio source.
- `Download -> Lyrics Lookup / Refresh` can start earlier, but must be refreshed if the final title/artist changes after metadata selection.
- `Lyrics Lookup / Refresh -> Tagging` after lyrics are fetched or after a best-effort timeout/error.
- `Tagging -> Finalize` after the file has been updated with metadata, artwork, and lyrics when available.

### Stop Rules

- Prefer iTunes metadata whenever it is available and coherent.
- Allow Spotify only as a short-timeout fallback or duration cross-check.
- Re-run YouTube search at most twice per song.
- Allow best-effort batch runs when the input contains multiple song requests separated by newlines or semicolons.
- Accept partial success when audio downloads successfully but lyrics or tagging metadata are incomplete.
- Fail only when no valid audio candidate can be selected or downloaded, or when the controller exceeds its retry budget.

### Selection Notes

- Featured artists should follow the canonical provider metadata when available.
- Manual fallback title cleanup is reserved for cases where no reliable metadata is available.
- Live, open session, performance, acoustic, unplugged, and similar session-style YouTube uploads are treated as noisy candidates unless the user explicitly asks for that version.
- When iTunes and Spotify both fail, fallback metadata inference should use the YouTube title, description, and thumbnail only.
- Song versions such as `- Remix` or `- Live` should remain explicit in the title when they are part of the version identity.
