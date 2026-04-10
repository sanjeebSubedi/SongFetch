import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src import (
    DownloadAudioSelection,
    MetadataLookupRequest,
    MetadataSelection,
    OllamaConfig,
    SongRequest,
    build_metadata_lookup_request,
    select_metadata_match,
    select_download_audio_request,
    build_song_request,
    parse_download_request,
)
from src.agents.download_selector import agent as download_selector_agent
from src.agents.metadata_request_builder import agent as metadata_request_builder
from src.agents.metadata_selector import agent as metadata_selector_agent
from src.agents.search_query_builder import agent as search_query_builder
from src.providers import ollama as ollama_provider


class FakeClient:
    last_host = None
    last_kwargs = None
    response_content = ""

    def __init__(self, *, host: str):
        type(self).last_host = host

    def chat(self, **kwargs):
        type(self).last_kwargs = kwargs
        return SimpleNamespace(message=SimpleNamespace(content=type(self).response_content))


class OllamaRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeClient.last_host = None
        FakeClient.last_kwargs = None
        FakeClient.response_content = ""

    def test_generate_structured_response_uses_ollama_config(self) -> None:
        FakeClient.response_content = json.dumps(
            {
                "song_name": "Yellow",
                "artist": "Coldplay",
                "album": None,
                "format": "m4a",
                "search_query": "Coldplay Yellow official audio",
            }
        )
        config = OllamaConfig(
            model="gemma4:e4b",
            host="http://localhost:11434",
            temperature=0.25,
        )

        with patch.object(
            ollama_provider,
            "build_ollama_client",
            return_value=FakeClient(host=config.host),
        ):
            result = ollama_provider.generate_structured_response(
                user_input="download Yellow by Coldplay",
                response_model=SongRequest,
                system_prompt="test prompt",
                config=config,
            )

        self.assertIsInstance(result, SongRequest)
        self.assertEqual(FakeClient.last_kwargs["model"], "gemma4:e4b")
        self.assertEqual(FakeClient.last_kwargs["format"], SongRequest.model_json_schema())
        self.assertEqual(FakeClient.last_kwargs["options"], {"temperature": 0.25})
        self.assertEqual(FakeClient.last_kwargs["messages"][0]["content"], "test prompt")
        self.assertEqual(
            FakeClient.last_kwargs["messages"][1]["content"],
            "download Yellow by Coldplay",
        )

    def test_generate_structured_response_surfaces_validation_debug_details(self) -> None:
        FakeClient.response_content = '{"song_name":"Yellow","artist":"Coldplay","format":"aac"}'
        config = OllamaConfig(
            model="gemma4:e4b",
            host="http://localhost:11434",
            temperature=0,
        )

        with patch.object(
            ollama_provider,
            "build_ollama_client",
            return_value=FakeClient(host=config.host),
        ):
            with self.assertRaises(RuntimeError) as context:
                ollama_provider.generate_structured_response(
                    user_input="download Yellow by Coldplay",
                    response_model=SongRequest,
                    system_prompt="test prompt",
                    config=config,
                )

        error_message = str(context.exception)
        self.assertIn("Validation errors:", error_message)
        self.assertIn("Raw response preview:", error_message)
        self.assertIn('"format":"aac"', error_message)

    def test_generate_structured_response_accepts_markdown_fenced_json(self) -> None:
        FakeClient.response_content = """```json
{
  "song_name": "Blinding Lights",
  "artist": null,
  "album": null,
  "format": "m4a",
  "search_query": "Blinding Lights"
}
```"""
        config = OllamaConfig(
            model="gemma4:e4b",
            host="http://localhost:11434",
            temperature=0,
        )

        with patch.object(
            ollama_provider,
            "build_ollama_client",
            return_value=FakeClient(host=config.host),
        ):
            result = ollama_provider.generate_structured_response(
                user_input="download the song Blinding Lights",
                response_model=SongRequest,
                system_prompt="test prompt",
                config=config,
            )

        self.assertIsInstance(result, SongRequest)
        self.assertEqual(result.song_name, "Blinding Lights")
        self.assertEqual(result.format, "m4a")


class SearchQueryBuilderTests(unittest.TestCase):
    def test_build_song_request_returns_song_request_model(self) -> None:
        song_request = SongRequest(
            song_name="Yellow",
            artist="Coldplay",
            album=None,
            format="m4a",
            search_query="Coldplay Yellow official audio",
        )

        with patch.object(
            search_query_builder,
            "generate_structured_response",
            return_value=song_request,
        ):
            result = build_song_request("download Yellow by Coldplay")

        self.assertIs(result, song_request)

    def test_build_song_request_passes_config_and_prompt(self) -> None:
        song_request = SongRequest(
            song_name="Yellow",
            artist="Coldplay",
            album=None,
            format="mp3",
            search_query="Coldplay Yellow official audio",
        )

        with patch.object(
            search_query_builder,
            "generate_structured_response",
            return_value=song_request,
        ) as mock_generate:
            parse_download_request(
                "download Yellow by Coldplay",
                host="http://localhost:11434",
                temperature=0.1,
            )

        kwargs = mock_generate.call_args.kwargs
        self.assertEqual(kwargs["user_input"], "download Yellow by Coldplay")
        self.assertIs(kwargs["response_model"], SongRequest)
        self.assertIn("search query builder", kwargs["system_prompt"].lower())
        self.assertEqual(kwargs["config"].host, "http://localhost:11434")
        self.assertEqual(kwargs["config"].temperature, 0.1)

    def test_song_request_schema_exposes_mp3_and_m4a_enum(self) -> None:
        schema = SongRequest.model_json_schema()
        format_schema = schema["properties"]["format"]

        self.assertEqual(format_schema["enum"], ["mp3", "m4a"])
        self.assertEqual(format_schema["default"], "m4a")


class MetadataRequestBuilderTests(unittest.TestCase):
    def test_build_metadata_lookup_request_returns_model(self) -> None:
        metadata_request = MetadataLookupRequest(
            song_name="Yellow",
            artist="Coldplay",
            reasoning="The official Coldplay upload has the highest views.",
        )
        search_results = [
            {
                "id": "abc123",
                "title": "Coldplay - Yellow (Official Video)",
                "uploader": "Coldplay",
                "duration_seconds": 269,
                "webpage_url": "https://www.youtube.com/watch?v=abc123",
                "view_count": 100,
            }
        ]

        with patch.object(
            metadata_request_builder,
            "generate_structured_response",
            return_value=metadata_request,
        ):
            result = build_metadata_lookup_request(
                "download Yellow by Coldplay",
                search_results,
            )

        self.assertIs(result, metadata_request)

    def test_build_metadata_lookup_request_passes_search_context_and_prompt(self) -> None:
        metadata_request = MetadataLookupRequest(
            song_name="Yellow",
            artist="Coldplay",
            reasoning="Coldplay appears consistently across the top results.",
        )
        search_results = [
            {
                "id": "abc123",
                "title": "Coldplay - Yellow (Official Video)",
                "uploader": "Coldplay",
                "duration_seconds": 269,
                "webpage_url": "https://www.youtube.com/watch?v=abc123",
                "view_count": 100,
            },
            {
                "id": "def456",
                "title": "Yellow",
                "uploader": "Coldplay - Topic",
                "duration_seconds": 266,
                "webpage_url": "https://www.youtube.com/watch?v=def456",
                "view_count": 90,
            },
        ]

        with patch.object(
            metadata_request_builder,
            "generate_structured_response",
            return_value=metadata_request,
        ) as mock_generate:
            build_metadata_lookup_request(
                "download Yellow by Coldplay",
                search_results,
                host="http://localhost:11434",
                temperature=0.1,
            )

        kwargs = mock_generate.call_args.kwargs
        payload = json.loads(kwargs["user_input"])
        self.assertEqual(payload["original_user_request"], "download Yellow by Coldplay")
        self.assertEqual(payload["youtube_search_results"][0]["title"], search_results[0]["title"])
        self.assertEqual(
            payload["youtube_search_results"][0]["uploader"],
            search_results[0]["uploader"],
        )
        self.assertEqual(
            payload["youtube_search_results"][0]["view_count"],
            search_results[0]["view_count"],
        )
        self.assertIs(kwargs["response_model"], MetadataLookupRequest)
        self.assertIn("music metadata analyst", kwargs["system_prompt"].lower())
        self.assertEqual(kwargs["config"].host, "http://localhost:11434")
        self.assertEqual(kwargs["config"].temperature, 0.1)

    def test_build_metadata_lookup_request_requires_search_results(self) -> None:
        with self.assertRaises(ValueError):
            build_metadata_lookup_request("download Yellow by Coldplay", [])


class MetadataSelectorTests(unittest.TestCase):
    def test_select_metadata_match_returns_model(self) -> None:
        selection = MetadataSelection(
            recording_id="recording-1",
            release_group_id="release-group-1",
            title="Yellow",
            artist="Coldplay",
            album="Parachutes",
            duration_ms=266000,
            is_explicit=True,
            reason="Earliest non-compilation studio release with valid length.",
        )
        metadata_matches = [
            {
                "recording_id": "recording-1",
                "release_group_id": "release-group-1",
                "release_group_primary_type": "Album",
                "release_group_secondary_types": None,
                "release_status": "Official",
                "title": "Yellow",
                "artist": "Coldplay",
                "artist_credit": "Coldplay",
                "album": "Parachutes",
                "first_release_date": "2000-06-26",
                "length_ms": 266000,
                "score": 100,
                "disambiguation": None,
                "musicbrainz_url": "https://musicbrainz.org/recording/recording-1",
            }
        ]

        with patch.object(
            metadata_selector_agent,
            "generate_structured_response",
            return_value=selection,
        ):
            result = select_metadata_match(
                "download Yellow by Coldplay",
                metadata_matches,
            )

        self.assertIs(result, selection)

    def test_select_metadata_match_passes_metadata_candidates_to_model(self) -> None:
        selection = MetadataSelection(
            recording_id="recording-1",
            release_group_id="release-group-1",
            title="Yellow",
            artist="Coldplay",
            album="Parachutes",
            duration_ms=266000,
            is_explicit=True,
            reason="Best studio candidate.",
        )
        metadata_matches = [
            {
                "recording_id": "recording-1",
                "release_group_id": "release-group-1",
                "release_group_primary_type": "Album",
                "release_group_secondary_types": None,
                "release_status": "Official",
                "title": "Yellow",
                "artist": "Coldplay",
                "artist_credit": "Coldplay",
                "album": "Parachutes",
                "first_release_date": "2000-06-26",
                "length_ms": 266000,
                "score": 100,
                "disambiguation": None,
                "musicbrainz_url": "https://musicbrainz.org/recording/recording-1",
            }
        ]

        with patch.object(
            metadata_selector_agent,
            "generate_structured_response",
            return_value=selection,
        ) as mock_generate:
            select_metadata_match(
                "download Yellow by Coldplay",
                metadata_matches,
                host="http://localhost:11434",
                temperature=0.1,
            )

        kwargs = mock_generate.call_args.kwargs
        payload = json.loads(kwargs["user_input"])
        self.assertEqual(payload["original_user_request"], "download Yellow by Coldplay")
        self.assertEqual(
            payload["musicbrainz_candidates"][0]["release_group_id"],
            "release-group-1",
        )
        self.assertIs(kwargs["response_model"], MetadataSelection)
        self.assertIn("metadata selection assistant", kwargs["system_prompt"].lower())
        self.assertEqual(kwargs["config"].host, "http://localhost:11434")
        self.assertEqual(kwargs["config"].temperature, 0.1)

    def test_select_metadata_match_requires_candidates(self) -> None:
        with self.assertRaises(ValueError):
            select_metadata_match("download Yellow by Coldplay", [])

    def test_select_metadata_match_requires_release_group_id(self) -> None:
        metadata_matches = [
            {
                "recording_id": "recording-1",
                "release_group_id": None,
                "release_group_primary_type": "Album",
                "release_group_secondary_types": None,
                "release_status": "Official",
                "title": "Yellow",
                "artist": "Coldplay",
                "artist_credit": "Coldplay",
                "album": "Parachutes",
                "first_release_date": "2000-06-26",
                "length_ms": 266000,
                "score": 100,
                "disambiguation": None,
                "musicbrainz_url": "https://musicbrainz.org/recording/recording-1",
            }
        ]
        with self.assertRaises(ValueError):
            select_metadata_match("download Yellow by Coldplay", metadata_matches)


class DownloadSelectorTests(unittest.TestCase):
    def test_select_download_audio_request_returns_model(self) -> None:
        metadata_selection = MetadataSelection(
            recording_id="recording-1",
            release_group_id="release-group-1",
            title="Yellow",
            artist="Coldplay",
            album="Parachutes",
            duration_ms=266000,
            is_explicit=True,
            reason="Canonical studio release.",
        )
        search_results = [
            {
                "id": "abc123",
                "title": "Coldplay - Yellow (Official Video)",
                "uploader": "Coldplay",
                "duration_seconds": 269,
                "webpage_url": "https://www.youtube.com/watch?v=abc123",
                "view_count": 100,
            }
        ]
        selection = DownloadAudioSelection.model_validate(
            {
                "reasoning": "Duration closely matches metadata and source is official.",
                "tool_call": {
                    "tool": "download_audio",
                    "parameters": {
                        "url": "https://www.youtube.com/watch?v=abc123",
                        "format": "m4a",
                        "filename": "Coldplay - Yellow",
                    },
                },
            }
        )

        with patch.object(
            download_selector_agent,
            "generate_structured_response",
            return_value=selection,
        ):
            result = select_download_audio_request(
                "download Yellow by Coldplay",
                metadata_selection,
                search_results,
                requested_format="m4a",
            )

        self.assertIs(result, selection)

    def test_select_download_audio_request_passes_payload(self) -> None:
        metadata_selection = MetadataSelection(
            recording_id="recording-1",
            release_group_id="release-group-1",
            title="Yellow",
            artist="Coldplay",
            album="Parachutes",
            duration_ms=266000,
            is_explicit=True,
            reason="Canonical studio release.",
        )
        search_results = [
            {
                "id": "abc123",
                "title": "Coldplay - Yellow (Official Video)",
                "uploader": "Coldplay",
                "duration_seconds": 269,
                "webpage_url": "https://www.youtube.com/watch?v=abc123",
                "view_count": 100,
            }
        ]
        selection = DownloadAudioSelection.model_validate(
            {
                "reasoning": "Best match.",
                "tool_call": {
                    "tool": "download_audio",
                    "parameters": {
                        "url": "https://www.youtube.com/watch?v=abc123",
                        "format": "m4a",
                        "filename": "Coldplay - Yellow",
                    },
                },
            }
        )

        with patch.object(
            download_selector_agent,
            "generate_structured_response",
            return_value=selection,
        ) as mock_generate:
            select_download_audio_request(
                "download Yellow by Coldplay as m4a",
                metadata_selection,
                search_results,
                requested_format="m4a",
                host="http://localhost:11434",
                temperature=0.1,
            )

        kwargs = mock_generate.call_args.kwargs
        payload = json.loads(kwargs["user_input"])
        self.assertEqual(
            payload["original_user_request"],
            "download Yellow by Coldplay as m4a",
        )
        self.assertEqual(payload["requested_format"], "m4a")
        self.assertEqual(
            payload["reference_metadata"]["recording_id"],
            "recording-1",
        )
        self.assertEqual(payload["reference_metadata"]["duration_seconds"], 266)
        self.assertNotIn("duration_ms", payload["reference_metadata"])
        self.assertEqual(
            payload["youtube_candidates"][0]["webpage_url"],
            "https://www.youtube.com/watch?v=abc123",
        )
        self.assertIs(kwargs["response_model"], DownloadAudioSelection)
        self.assertIn("technical procurement officer", kwargs["system_prompt"].lower())
        self.assertEqual(kwargs["config"].host, "http://localhost:11434")
        self.assertEqual(kwargs["config"].temperature, 0.1)

    def test_select_download_audio_request_requires_candidates(self) -> None:
        metadata_selection = MetadataSelection(
            recording_id="recording-1",
            release_group_id="release-group-1",
            title="Yellow",
            artist="Coldplay",
            album="Parachutes",
            duration_ms=266000,
            is_explicit=True,
            reason="Canonical studio release.",
        )
        with self.assertRaises(ValueError):
            select_download_audio_request(
                "download Yellow by Coldplay",
                metadata_selection,
                [],
                requested_format="m4a",
            )


if __name__ == "__main__":
    unittest.main()
