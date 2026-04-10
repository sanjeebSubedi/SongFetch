# Audio Agent

This project now uses a single root `main.py` entry point, with the reusable code organized
under `src/`:

```text
main.py
src/
  __init__.py
  agents/
    __init__.py
    _shared.py
    metadata_request_builder/
      __init__.py
      agent.py
      prompt.py
      schema.py
    metadata_selector/
      __init__.py
      agent.py
      prompt.py
      schema.py
    download_selector/
      __init__.py
      agent.py
      prompt.py
      schema.py
    search_query_builder/
      __init__.py
      agent.py
      prompt.py
      schema.py
  providers/
    __init__.py
    itunes.py
    ollama.py
  types.py
  tools/
    __init__.py
    _shared.py
    metadata.py
    search.py
    download.py
    tagging.py
```

It currently exposes these main entry points for the workflow:

- `search_song_audio(query, limit=5)`
- `download_song_audio(url, output_dir="downloads", audio_format="m4a")`
- `fetch_music_metadata(song_name, artist=None, album=None, limit=5)`
- `fetch_metadata_from_search_results(user_input, search_results, limit=5)`
- `select_metadata_match(user_input, metadata_matches)`
- `select_download_audio_request(user_input, metadata_selection, search_results, requested_format)`
- `parse_download_request(user_input, model="gemma4:e4b")`

The model-powered part of the app is split by responsibility:

`src/providers/ollama.py`
- shared Ollama config and structured-response loading

`src/providers/itunes.py`
- shared iTunes Search API access for track metadata

`src/agents/search_query_builder/agent.py`
- the song request agent prompt and schema wiring

`src/agents/metadata_request_builder/agent.py`
- the metadata lookup agent that turns YouTube results into canonical `song_name` and `artist`

`src/agents/metadata_selector/agent.py`
- the metadata selector agent that chooses one canonical iTunes track match from candidates

`src/agents/download_selector/agent.py`
- the download selector agent that chooses one YouTube URL and builds `download_audio` args

`src/agents/search_query_builder/schema.py`
- the `SongRequest` schema for this specific agent

`src/agents/metadata_request_builder/schema.py`
- the `MetadataLookupRequest` schema for the metadata lookup step

`src/agents/metadata_selector/schema.py`
- the `MetadataSelection` schema for the final canonical metadata selection step

`src/agents/download_selector/schema.py`
- the `DownloadAudioSelection` schema for the URL and download tool arguments

`src/agents/search_query_builder/prompt.py`
- reusable prompt text for the search query builder

`src/agents/metadata_request_builder/prompt.py`
- reusable prompt text for extracting canonical metadata lookup inputs

`main.py`
- the single CLI entry point that runs the currently implemented pipeline stages end to end

You can import the schema as:

```python
from src.agents import SongRequest
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Install `ffmpeg` locally as well, since the default output format is `m4a`.
The pipeline also uses `mutagen` to embed selected metadata tags into the downloaded file.

To use the LLM parser, make sure Ollama is running locally and that `gemma4:31b-cloud` is available.

## Example

```python
from src import SongRequest, build_song_request, download_song_audio, search_song_audio

song_request = build_song_request("download Yellow by Coldplay as m4a")
results = search_song_audio(song_request.search_query, limit=3)

selected_url = results[0]["webpage_url"]
download = download_song_audio(selected_url)
print(download["output_path"])
```

If you want to wire the query builder directly into the search tool from code:

```python
from src.tools.search import search_from_request

matches = search_from_request("download Yellow by Coldplay as m4a", limit=5)
print(matches)
```

If you want to fetch normalized metadata from the iTunes Search API:

```python
from src import fetch_music_metadata

metadata_matches = fetch_music_metadata("Yellow", artist="Coldplay", album="Parachutes", limit=5)
print(metadata_matches)
```

If you want to wire the existing search flow into the metadata tool:

```python
from src.tools.metadata import fetch_metadata_from_search_results
from src.tools.search import search_from_request

user_input = "download Yellow by Coldplay as m4a"
search_results = search_from_request(user_input, limit=5)
metadata_matches = fetch_metadata_from_search_results(user_input, search_results, limit=5)
print(metadata_matches)
```

For live iTunes Search API usage, you can override the storefront with `ITUNES_COUNTRY`
or the `main.py` `--itunes-country` flag.

## Run The Pipeline

Run the current pipeline from natural-language request to YouTube search results and iTunes
metadata matches:

```bash
.venv/bin/python main.py "download Yellow by Coldplay as m4a" --search-limit 5 --metadata-limit 5
```

The JSON output currently includes:

- `song_request`
- `search_results`
- `metadata_lookup_request`
- `metadata_matches`
- `selected_metadata`
- `selected_download`
- `download_result`
- `tagging_result`
