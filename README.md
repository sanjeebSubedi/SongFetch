# Audio Agent

An agentic music retrieval pipeline that turns rough song requests into downloadable audio files with best-effort metadata and tagging.

It is built to handle the kinds of requests people actually type: misspellings, lyric snippets, multiple songs, and playlists. The system combines LLM-guided decisions with deterministic tools so it can recover clean results without requiring perfect input.

## Highlights

- Single-song, batch, and Spotify playlist support
- Best-effort metadata and lyrics tagging
- Audio-focused retrieval for cleaner downloads
- Fallback artwork and metadata when providers are incomplete
- State-driven orchestration rather than a rigid linear script

## Stack

- Python 3.12+
- Ollama (install from https://ollama.com if it is not already on your machine)
- yt-dlp
- iTunes Search API
- Spotify scraping fallback
- LRCLIB
- mutagen

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Copy `.env.example` to `.env` to customize runtime settings.

This project defaults to `gemma4:31b-cloud`, which requires `ollama signin` before use.

Local Ollama setup:

```bash
ollama signin
```

## Docker

```bash
docker compose up -d ollama
docker compose exec ollama ollama signin
docker compose run --rm app "download Yellow by Coldplay as m4a"
```

The Docker setup starts an Ollama server alongside the app and keeps Ollama state in a Docker volume, so sign-in only needs to happen once per volume.
The app container also keeps its local cache in a repo-local bind mount to avoid transient Selenium cache issues.

## Usage

Single song:

```bash
.venv/bin/python main.py "download Yellow by Coldplay as m4a"
```

Playlist:

```bash
.venv/bin/python main.py --spotify-playlist "https://open.spotify.com/playlist/PLAYLIST_ID"
```

Batch input:

```bash
.venv/bin/python main.py "download Yellow by Coldplay\ndownload Fix You by Coldplay"
```

Tests:

```bash
.venv/bin/python -m pytest tests/
```

## Notes

- Outside Docker, the app expects an Ollama host to be available.
- The default model is `gemma4:31b-cloud`, so Ollama Cloud sign-in is required.
- OpenAI API compatibility is coming soon.
- iTunes is the preferred metadata source.
- Spotify is used as a fallback when needed.
- When metadata providers fail, the pipeline still returns a best-effort result.

## Layout

- `main.py` - CLI entry point
- `src/pipeline.py` - orchestration layer
- `src/agents/` - LLM-backed request and selection agents
- `src/tools/` - download, search, metadata, lyrics, and tagging utilities
- `src/providers/` - service clients and configs
- `tests/` - unit and integration tests
