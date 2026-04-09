# Audio Agent

This project is structured as a small Python package so the tool layer is easy to grow:

```text
audio_agent/
  __init__.py
  agents/
    __init__.py
    search_query_builder/
      __init__.py
      agent.py
      prompt.py
      schema.py
  providers/
    __init__.py
    ollama.py
  types.py
  tools/
    __init__.py
    _shared.py
    search.py
    download.py
```

It currently exposes these main entry points for the workflow:

- `search_song_audio(query, limit=5)`
- `download_song_audio(url, output_dir="downloads", audio_format="m4a")`
- `parse_download_request(user_input, model="gemma4:e4b")`

The model-powered part of the app is split by responsibility:

`audio_agent/providers/ollama.py`
- shared Ollama config and structured-response loading

`audio_agent/agents/search_query_builder/agent.py`
- the song request agent prompt, schema wiring, and CLI entry point

`audio_agent/agents/search_query_builder/schema.py`
- the `SongRequest` schema for this specific agent

`audio_agent/agents/search_query_builder/prompt.py`
- reusable prompt text and prompt-building helpers for this specific agent

You can import the schema as:

```python
from audio_agent.agents import SongRequest
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Install `ffmpeg` locally as well, since the default output format is `m4a`.

To use the LLM parser, make sure Ollama is running locally and that `gemma4:e4b` is available.

## Example

```python
from audio_agent import SongRequest, build_song_request, download_song_audio, search_song_audio

song_request = build_song_request("download Yellow by Coldplay as m4a")
results = search_song_audio(song_request.search_query, limit=3)

selected_url = results[0]["webpage_url"]
download = download_song_audio(selected_url)
print(download["output_path"])
```

If you want to wire the query builder directly into the search tool from code:

```python
from audio_agent.tools.search import search_from_request

matches = search_from_request("download Yellow by Coldplay as m4a", limit=5)
print(matches)
```

## CLI Checks

Run the search tool through the query builder:

```bash
.venv/bin/python -m audio_agent.tools.search "download Yellow by Coldplay as m4a" --limit 5
```

Run the search tool with a direct raw YouTube query instead:

```bash
.venv/bin/python -m audio_agent.tools.search "Coldplay Yellow official audio" --direct-query --limit 5
```
