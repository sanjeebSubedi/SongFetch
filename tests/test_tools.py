import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src import SongRequest, download_song_audio, search_song_audio
from src.tools import download as download_module
from src.tools import search as search_module
from src.tools import tagging as tagging_module


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

    def test_download_song_audio_respects_custom_filename(self) -> None:
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
                download_song_audio(
                    "https://www.youtube.com/watch?v=abc123",
                    output_dir=Path("/tmp/audio-agent-tests"),
                    filename="Coldplay: Yellow?",
                )

        self.assertEqual(
            FakeYoutubeDL.last_options["outtmpl"],
            "/tmp/audio-agent-tests/Coldplay Yellow.%(ext)s",
        )

    def test_embed_selected_metadata_tags_mp4(self) -> None:
        class FakeMP4File:
            def __init__(self, path):
                self.path = path
                self.tags = None
                self.saved = False

            def add_tags(self):
                self.tags = {}

            def save(self):
                self.saved = True

        mp4_file = FakeMP4File("dummy.m4a")
        metadata = SimpleNamespace(
            title="Yellow",
            artist="Coldplay",
            album="Parachutes",
        )

        with patch.object(tagging_module, "_load_mutagen_mp4", return_value=lambda _: mp4_file):
            result = tagging_module.embed_selected_metadata("dummy.m4a", metadata)

        self.assertEqual(result, {"path": "dummy.m4a", "container": "m4a"})
        self.assertEqual(mp4_file.tags["\xa9nam"], ["Yellow"])
        self.assertEqual(mp4_file.tags["\xa9ART"], ["Coldplay"])
        self.assertEqual(mp4_file.tags["\xa9alb"], ["Parachutes"])
        self.assertTrue(mp4_file.saved)

    def test_embed_selected_metadata_tags_mp3(self) -> None:
        class FakeEasyID3(dict):
            def __init__(self, _path=None):
                super().__init__()
                self.saved_path = None

            def save(self, path=None):
                self.saved_path = path

        metadata = SimpleNamespace(
            title="Yellow",
            artist="Coldplay",
            album="Parachutes",
        )

        with patch.object(
            tagging_module,
            "_load_mutagen_easyid3",
            return_value=(FakeEasyID3, RuntimeError),
        ):
            result = tagging_module.embed_selected_metadata("dummy.mp3", metadata)

        self.assertEqual(result, {"path": "dummy.mp3", "container": "mp3"})

    def test_embed_selected_metadata_rejects_unsupported_extension(self) -> None:
        metadata = SimpleNamespace(
            title="Yellow",
            artist="Coldplay",
            album="Parachutes",
        )
        with self.assertRaises(ValueError):
            tagging_module.embed_selected_metadata("dummy.wav", metadata)


if __name__ == "__main__":
    unittest.main()
