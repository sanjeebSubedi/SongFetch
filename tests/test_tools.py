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
                    "description": None,
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
        class FakeMP4Cover:
            FORMAT_JPEG = 13
            FORMAT_PNG = 14

            def __init__(self, data, imageformat):
                self.data = data
                self.imageformat = imageformat

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
            artwork_url="https://example.com/100x100bb.jpg",
        )

        with patch.object(
            tagging_module,
            "_load_mutagen_mp4",
            return_value=(lambda _: mp4_file, FakeMP4Cover),
        ):
            with patch.object(
                tagging_module,
                "_fetch_cover_art",
                return_value=(b"jpeg-bytes", "image/jpeg"),
            ):
                result = tagging_module.embed_selected_metadata("dummy.m4a", metadata)

        self.assertEqual(
            result,
            {
                "path": "dummy.m4a",
                "container": "m4a",
                "artwork_embedded": True,
                "lyrics_embedded": False,
            },
        )
        self.assertEqual(mp4_file.tags["\xa9nam"], ["Yellow"])
        self.assertEqual(mp4_file.tags["\xa9ART"], ["Coldplay"])
        self.assertEqual(mp4_file.tags["\xa9alb"], ["Parachutes"])
        self.assertEqual(len(mp4_file.tags["covr"]), 1)
        self.assertEqual(mp4_file.tags["covr"][0].data, b"jpeg-bytes")
        self.assertEqual(mp4_file.tags["covr"][0].imageformat, FakeMP4Cover.FORMAT_JPEG)
        self.assertTrue(mp4_file.saved)

    def test_embed_selected_metadata_tags_mp3(self) -> None:
        class FakeEasyID3(dict):
            def __init__(self, _path=None):
                super().__init__()
                self.saved_path = None

            def save(self, path=None):
                self.saved_path = path

        class FakeID3:
            last_instance = None

            def __init__(self, path):
                self.path = path
                self.deleted_keys = []
                self.added_frames = []
                self.saved = False
                type(self).last_instance = self

            def delall(self, key):
                self.deleted_keys.append(key)

            def add(self, frame):
                self.added_frames.append(frame)

            def save(self):
                self.saved = True

        def fake_apic(**kwargs):
            return kwargs

        def fake_uslt(**kwargs):
            return kwargs

        metadata = SimpleNamespace(
            title="Yellow",
            artist="Coldplay",
            album="Parachutes",
            artwork_url="https://example.com/100x100bb.jpg",
        )

        with patch.object(
            tagging_module,
            "_load_mutagen_easyid3",
            return_value=(FakeEasyID3, RuntimeError),
        ):
            with patch.object(
                tagging_module,
                "_load_mutagen_id3",
                return_value=(FakeID3, fake_apic, fake_uslt),
            ):
                with patch.object(
                    tagging_module,
                    "_fetch_cover_art",
                    return_value=(b"png-bytes", "image/png"),
                ):
                    result = tagging_module.embed_selected_metadata("dummy.mp3", metadata)

        self.assertEqual(
            result,
            {
                "path": "dummy.mp3",
                "container": "mp3",
                "artwork_embedded": True,
                "lyrics_embedded": False,
            },
        )
        self.assertEqual(FakeID3.last_instance.deleted_keys, ["APIC"])
        self.assertEqual(FakeID3.last_instance.added_frames[0]["mime"], "image/png")
        self.assertEqual(FakeID3.last_instance.added_frames[0]["data"], b"png-bytes")
        self.assertTrue(FakeID3.last_instance.saved)

    def test_embed_selected_metadata_without_artwork_reports_false(self) -> None:
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

        with patch.object(
            tagging_module,
            "_load_mutagen_mp4",
            return_value=(lambda _: mp4_file, object),
        ):
            with patch.object(tagging_module, "_fetch_cover_art", return_value=None):
                result = tagging_module.embed_selected_metadata("dummy.m4a", metadata)

        self.assertEqual(
            result,
            {
                "path": "dummy.m4a",
                "container": "m4a",
                "artwork_embedded": False,
                "lyrics_embedded": False,
            },
        )

    def test_embed_selected_metadata_embeds_mp4_lyrics(self) -> None:
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
            artwork_url=None,
        )

        with patch.object(
            tagging_module,
            "_load_mutagen_mp4",
            return_value=(lambda _: mp4_file, object),
        ):
            with patch.object(tagging_module, "_fetch_cover_art", return_value=None):
                result = tagging_module.embed_selected_metadata(
                    "dummy.m4a",
                    metadata,
                    lyrics="Look at the stars",
                )

        self.assertEqual(mp4_file.tags["\xa9lyr"], ["Look at the stars"])
        self.assertEqual(
            result["lyrics_embedded"],
            True,
        )

    def test_embed_selected_metadata_embeds_mp3_lyrics(self) -> None:
        class FakeEasyID3(dict):
            def __init__(self, _path=None):
                super().__init__()
                self.saved_path = None

            def save(self, path=None):
                self.saved_path = path

        class FakeID3:
            last_instance = None

            def __init__(self, path):
                self.path = path
                self.deleted_keys = []
                self.added_frames = []
                self.saved = False
                type(self).last_instance = self

            def delall(self, key):
                self.deleted_keys.append(key)

            def add(self, frame):
                self.added_frames.append(frame)

            def save(self):
                self.saved = True

        def fake_apic(**kwargs):
            return kwargs

        def fake_uslt(**kwargs):
            return kwargs

        metadata = SimpleNamespace(
            title="Yellow",
            artist="Coldplay",
            album="Parachutes",
            artwork_url=None,
        )

        with patch.object(
            tagging_module,
            "_load_mutagen_easyid3",
            return_value=(FakeEasyID3, RuntimeError),
        ):
            with patch.object(
                tagging_module,
                "_load_mutagen_id3",
                return_value=(FakeID3, fake_apic, fake_uslt),
            ):
                with patch.object(tagging_module, "_fetch_cover_art", return_value=None):
                    result = tagging_module.embed_selected_metadata(
                        "dummy.mp3",
                        metadata,
                        lyrics="Look at the stars",
                    )

        self.assertEqual(FakeID3.last_instance.deleted_keys, ["USLT"])
        self.assertEqual(FakeID3.last_instance.added_frames[0]["text"], "Look at the stars")
        self.assertEqual(result["lyrics_embedded"], True)

    def test_artwork_candidate_urls_prefers_higher_resolutions(self) -> None:
        candidates = tagging_module._artwork_candidate_urls(
            "https://is1-ssl.mzstatic.com/image/thumb/Music126/v4/ab/cd/ef/100x100bb.jpg"
        )

        self.assertEqual(
            candidates[0],
            "https://is1-ssl.mzstatic.com/image/thumb/Music126/v4/ab/cd/ef/3000x3000bb.jpg",
        )
        self.assertIn(
            "https://is1-ssl.mzstatic.com/image/thumb/Music126/v4/ab/cd/ef/100x100bb.jpg",
            candidates,
        )

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
