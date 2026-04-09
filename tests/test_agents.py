import json
import unittest
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from audio_agent import OllamaConfig, SongRequest, build_song_request, parse_download_request
from audio_agent.agents.search_query_builder import agent as search_query_builder
from audio_agent.providers import ollama as ollama_provider


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

    def test_main_prints_model_json_output(self) -> None:
        stdout = StringIO()
        song_request = SongRequest(
            song_name="Yellow",
            artist="Coldplay",
            album=None,
            format="m4a",
            search_query="Coldplay Yellow official audio",
        )

        with patch.object(search_query_builder, "build_song_request", return_value=song_request):
            with patch("sys.stdout", stdout):
                exit_code = search_query_builder.main(["download", "Yellow", "by", "Coldplay"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue()), song_request.model_dump())


if __name__ == "__main__":
    unittest.main()
