import json
import unittest
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from audio_agent import SongRequest, download_song_audio, search_song_audio
from audio_agent.tools import download as download_module
from audio_agent.tools import search as search_module


class FakeYoutubeDL:
    last_options = None
    last_query = None
    last_download_flag = None
    response: dict = {}

    def __init__(self, options):
        type(self).last_options = options

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def extract_info(self, query, download=False):
        type(self).last_query = query
        type(self).last_download_flag = download
        return type(self).response


class ToolTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeYoutubeDL.last_options = None
        FakeYoutubeDL.last_query = None
        FakeYoutubeDL.last_download_flag = None

    def test_search_song_audio_returns_simplified_results(self) -> None:
        FakeYoutubeDL.response = {
            "entries": [
                {
                    "id": "abc123",
                    "title": "Linkin Park - Numb",
                    "uploader": "Linkin Park",
                    "duration": 186,
                    "view_count": 42,
                }
            ]
        }

        with patch.object(
            search_module,
            "get_yt_dlp",
            return_value=SimpleNamespace(YoutubeDL=FakeYoutubeDL),
        ):
            results = search_song_audio("Numb", limit=3)

        self.assertEqual(FakeYoutubeDL.last_query, "ytsearch3:Numb")
        self.assertFalse(FakeYoutubeDL.last_download_flag)
        self.assertEqual(
            results,
            [
                {
                    "id": "abc123",
                    "title": "Linkin Park - Numb",
                    "uploader": "Linkin Park",
                    "duration_seconds": 186,
                    "webpage_url": "https://www.youtube.com/watch?v=abc123",
                    "view_count": 42,
                }
            ],
        )

    def test_search_from_request_uses_query_builder_output(self) -> None:
        song_request = SongRequest(
            song_name="Yellow",
            artist="Coldplay",
            album=None,
            format="m4a",
            search_query="Coldplay Yellow official audio",
        )
        matches = [
            {
                "id": "abc123",
                "title": "Coldplay - Yellow",
                "uploader": "Coldplay",
                "duration_seconds": 269,
                "webpage_url": "https://www.youtube.com/watch?v=abc123",
                "view_count": 42,
            }
        ]

        with patch.object(search_module, "build_song_request", return_value=song_request):
            with patch.object(search_module, "search_song_audio", return_value=matches) as mock_search:
                result = search_module.search_from_request(
                    "download Yellow by Coldplay",
                    limit=3,
                )

        self.assertEqual(result, matches)
        mock_search.assert_called_once_with("Coldplay Yellow official audio", limit=3)

    def test_search_tool_main_prints_matches_from_request(self) -> None:
        matches = [
            {
                "id": "abc123",
                "title": "Coldplay - Yellow",
                "uploader": "Coldplay",
                "duration_seconds": 269,
                "webpage_url": "https://www.youtube.com/watch?v=abc123",
                "view_count": 42,
            }
        ]
        stdout = StringIO()

        with patch.object(search_module, "search_from_request", return_value=matches):
            with patch("sys.stdout", stdout):
                exit_code = search_module.main(["download", "Yellow", "by", "Coldplay", "--limit", "3"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue()), matches)

    def test_search_tool_main_supports_direct_query_mode(self) -> None:
        FakeYoutubeDL.response = {
            "entries": [
                {
                    "id": "abc123",
                    "title": "Linkin Park - Numb",
                    "uploader": "Linkin Park",
                    "duration": 186,
                    "view_count": 42,
                }
            ]
        }
        stdout = StringIO()

        with patch.object(
            search_module,
            "get_yt_dlp",
            return_value=SimpleNamespace(YoutubeDL=FakeYoutubeDL),
        ):
            with patch("sys.stdout", stdout):
                exit_code = search_module.main(["Numb", "--direct-query", "--limit", "3"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            json.loads(stdout.getvalue()),
            [
                {
                    "id": "abc123",
                    "title": "Linkin Park - Numb",
                    "uploader": "Linkin Park",
                    "duration_seconds": 186,
                    "webpage_url": "https://www.youtube.com/watch?v=abc123",
                    "view_count": 42,
                }
            ],
        )

    def test_download_song_audio_defaults_to_m4a(self) -> None:
        FakeYoutubeDL.response = {
            "id": "abc123",
            "title": "Linkin Park - Numb",
            "_filename": "/tmp/Linkin Park - Numb.webm",
        }

        with patch.object(
            download_module,
            "get_yt_dlp",
            return_value=SimpleNamespace(YoutubeDL=FakeYoutubeDL),
        ):
            with patch.object(download_module.shutil, "which", return_value="/usr/bin/ffmpeg"):
                result = download_song_audio(
                    "https://www.youtube.com/watch?v=abc123",
                    output_dir=Path("/tmp/audio-agent-tests"),
                )

        self.assertTrue(FakeYoutubeDL.last_download_flag)
        self.assertEqual(
            FakeYoutubeDL.last_options["format"],
            "bestaudio[ext=m4a]/bestaudio/best",
        )
        self.assertEqual(
            FakeYoutubeDL.last_options["postprocessors"][0]["preferredcodec"],
            "m4a",
        )
        self.assertEqual(result["audio_format"], "m4a")
        self.assertEqual(result["output_path"], "/tmp/Linkin Park - Numb.m4a")

    def test_download_song_audio_best_does_not_require_ffmpeg(self) -> None:
        FakeYoutubeDL.response = {
            "id": "abc123",
            "title": "Linkin Park - Numb",
            "filepath": "/tmp/Linkin Park - Numb.webm",
        }

        with patch.object(
            download_module,
            "get_yt_dlp",
            return_value=SimpleNamespace(YoutubeDL=FakeYoutubeDL),
        ):
            with patch.object(download_module.shutil, "which", return_value=None):
                result = download_song_audio(
                    "https://www.youtube.com/watch?v=abc123",
                    audio_format="best",
                )

        self.assertNotIn("postprocessors", FakeYoutubeDL.last_options)
        self.assertEqual(result["output_path"], "/tmp/Linkin Park - Numb.webm")


if __name__ == "__main__":
    unittest.main()
