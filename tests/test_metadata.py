import json
import unittest
from unittest.mock import patch

from src import (
    MetadataLookupRequest,
    MusicBrainzConfig,
    SongRequest,
    fetch_metadata_from_request,
    fetch_metadata_from_search_results,
    fetch_music_metadata,
)
from src.providers import musicbrainz
from src.tools import metadata as metadata_tool


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class MusicBrainzProviderTests(unittest.TestCase):
    def test_search_recordings_sends_expected_request(self) -> None:
        captured_request = None
        payload = {"recordings": []}
        config = MusicBrainzConfig(
            base_url="https://musicbrainz.org/ws/2",
            user_agent="audio-agent-tests/1.0",
            rate_limit_seconds=0,
        )

        def fake_urlopen(raw_request, timeout=0):
            nonlocal captured_request
            captured_request = raw_request
            self.assertEqual(timeout, config.timeout_seconds)
            return FakeResponse(payload)

        with patch.object(musicbrainz.request, "urlopen", side_effect=fake_urlopen):
            result = musicbrainz.search_recordings(
                'recording:"Yellow" AND artist:"Coldplay"',
                limit=3,
                config=config,
            )

        self.assertEqual(result, payload)
        self.assertIsNotNone(captured_request)
        self.assertIn("/recording?", captured_request.full_url)
        self.assertIn("limit=3", captured_request.full_url)
        self.assertIn("fmt=json", captured_request.full_url)
        self.assertEqual(captured_request.headers["User-agent"], "audio-agent-tests/1.0")


class MetadataToolTests(unittest.TestCase):
    def test_fetch_music_metadata_normalizes_recordings(self) -> None:
        payload = {
            "recordings": [
                {
                    "id": "recording-1",
                    "title": "Yellow",
                    "length": 266000,
                    "score": "100",
                    "first-release-date": "2000-06-26",
                    "artist-credit": [
                        {
                            "name": "Coldplay",
                            "artist": {"name": "Coldplay"},
                        }
                    ],
                    "releases": [
                        {
                            "title": "Parachutes",
                        }
                    ],
                }
            ]
        }

        with patch.object(metadata_tool, "search_recordings", return_value=payload):
            result = fetch_music_metadata("Yellow", artist="Coldplay", album="Parachutes", limit=2)

        self.assertEqual(
            result,
            [
                {
                    "recording_id": "recording-1",
                    "release_group_id": None,
                    "release_group_primary_type": None,
                    "release_group_secondary_types": None,
                    "release_status": None,
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
            ],
        )

    def test_fetch_metadata_from_request_uses_song_request_fields(self) -> None:
        song_request = SongRequest(
            song_name="Yellow",
            artist="Coldplay",
            album="Parachutes",
            format="m4a",
            search_query="Coldplay Yellow official audio",
        )

        with patch.object(metadata_tool, "fetch_music_metadata", return_value=[]) as mock_fetch:
            fetch_metadata_from_request(song_request, limit=4)

        mock_fetch.assert_called_once_with(
            "Yellow",
            artist="Coldplay",
            album="Parachutes",
            limit=4,
            config=None,
        )

    def test_fetch_metadata_from_search_results_uses_model_output(self) -> None:
        metadata_request = MetadataLookupRequest(
            song_name="Yellow",
            artist="Coldplay",
            reasoning="Coldplay's official upload dominates the top results.",
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
            metadata_tool,
            "build_metadata_lookup_request",
            return_value=metadata_request,
        ) as mock_build_request:
            with patch.object(metadata_tool, "fetch_music_metadata", return_value=[]) as mock_fetch:
                fetch_metadata_from_search_results(
                    "download Yellow by Coldplay",
                    search_results,
                    limit=4,
                )

        mock_build_request.assert_called_once_with(
            "download Yellow by Coldplay",
            search_results,
            model="gemma4:e4b",
            host="http://127.0.0.1:11434",
            temperature=0,
        )
        mock_fetch.assert_called_once_with(
            "Yellow",
            artist="Coldplay",
            limit=4,
            config=None,
        )


if __name__ == "__main__":
    unittest.main()
