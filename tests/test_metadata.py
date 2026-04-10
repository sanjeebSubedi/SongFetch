import json
import unittest
from unittest.mock import patch

from src.providers.ollama import DEFAULT_OLLAMA_MODEL
from src import (
    ITunesConfig,
    LRCLibConfig,
    LyricsResult,
    MetadataLookupRequest,
    SongRequest,
    TagMetadata,
    fetch_lyrics,
    fetch_metadata_from_request,
    fetch_metadata_from_search_results,
    fetch_music_metadata,
)
from src.providers import itunes, lrclib
from src.tools import metadata as metadata_tool
from src.tools import lyrics as lyrics_tool


class FakeResponse:
    def __init__(self, payload: dict | list[dict], content_type: str = "application/json"):
        self.payload = payload
        self.headers = {"Content-Type": content_type}

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class ITunesProviderTests(unittest.TestCase):
    def test_search_songs_sends_expected_request(self) -> None:
        captured_request = None
        payload = {"results": []}
        config = ITunesConfig(
            base_url="https://itunes.apple.com/search",
            country="US",
        )

        def fake_urlopen(raw_request, timeout=0):
            nonlocal captured_request
            captured_request = raw_request
            self.assertEqual(timeout, config.timeout_seconds)
            return FakeResponse(payload)

        with patch.object(itunes.request, "urlopen", side_effect=fake_urlopen):
            result = itunes.search_songs(
                "Yellow Coldplay",
                limit=3,
                config=config,
            )

        self.assertEqual(result, payload)
        self.assertIsNotNone(captured_request)
        self.assertIn("term=Yellow+Coldplay", captured_request.full_url)
        self.assertIn("limit=3", captured_request.full_url)
        self.assertIn("entity=song", captured_request.full_url)
        self.assertIn("media=music", captured_request.full_url)
        self.assertIn("country=US", captured_request.full_url)


class LRCLibProviderTests(unittest.TestCase):
    def test_lookup_lyrics_returns_plain_lyrics(self) -> None:
        config = LRCLibConfig(base_url="https://lrclib.net/api")
        responses = [
            FakeResponse(
                {
                    "id": 1,
                    "trackName": "Yellow",
                    "artistName": "Coldplay",
                    "albumName": "Parachutes",
                    "duration": 266,
                    "plainLyrics": "Look at the stars",
                    "syncedLyrics": "[00:01.00]Look at the stars",
                }
            )
        ]

        def fake_urlopen(_request, timeout=0):
            self.assertEqual(timeout, config.timeout_seconds)
            return responses.pop(0)

        with patch.object(lrclib.request, "urlopen", side_effect=fake_urlopen):
            result = lrclib.lookup_lyrics(
                "Yellow",
                artist="Coldplay",
                album="Parachutes",
                duration_seconds=266,
                config=config,
            )

        self.assertEqual(
            result,
            LyricsResult(
                plain_lyrics="Look at the stars",
                source="lrclib",
                found=True,
                synced_available=True,
                synced_used=False,
            ),
        )

    def test_lookup_lyrics_uses_synced_lyrics_when_plain_missing(self) -> None:
        config = LRCLibConfig(base_url="https://lrclib.net/api")
        responses = [
            FakeResponse(
                {
                    "id": 1,
                    "trackName": "Yellow",
                    "artistName": "Coldplay",
                    "syncedLyrics": "[00:01.00]Look at the stars\n[00:02.00]Look how they shine",
                }
            )
        ]

        with patch.object(lrclib.request, "urlopen", side_effect=lambda *_args, **_kwargs: responses.pop(0)):
            result = lrclib.lookup_lyrics("Yellow", artist="Coldplay", config=config)

        self.assertEqual(result.plain_lyrics, "Look at the stars\nLook how they shine")
        self.assertTrue(result.synced_used)

    def test_lookup_lyrics_returns_none_when_not_found(self) -> None:
        config = LRCLibConfig(base_url="https://lrclib.net/api")

        def fake_urlopen(_request, timeout=0):
            raise lrclib.error.HTTPError(
                url="https://lrclib.net/api/get",
                code=404,
                msg="Not Found",
                hdrs=None,
                fp=None,
            )

        with patch.object(lrclib.request, "urlopen", side_effect=fake_urlopen):
            result = lrclib.lookup_lyrics("Unknown Song", artist="Unknown", config=config)

        self.assertIsNone(result)

    def test_lookup_lyrics_returns_none_on_network_error(self) -> None:
        config = LRCLibConfig(base_url="https://lrclib.net/api")

        with patch.object(
            lrclib.request,
            "urlopen",
            side_effect=lrclib.error.URLError("offline"),
        ):
            result = lrclib.lookup_lyrics("Yellow", artist="Coldplay", config=config)

        self.assertIsNone(result)


class MetadataToolTests(unittest.TestCase):
    def test_fetch_music_metadata_normalizes_itunes_results(self) -> None:
        payload = {
            "results": [
                {
                    "trackId": 123,
                    "collectionId": 456,
                    "trackName": "Yellow",
                    "artistName": "Coldplay",
                    "collectionName": "Parachutes",
                    "releaseDate": "2000-06-26T07:00:00Z",
                    "trackTimeMillis": 266000,
                    "trackExplicitness": "notExplicit",
                    "trackNumber": 5,
                    "discNumber": 1,
                    "primaryGenreName": "Alternative",
                    "artworkUrl100": "https://example.com/art.jpg",
                    "previewUrl": "https://example.com/preview.m4a",
                    "trackViewUrl": "https://music.apple.com/us/song/yellow/123",
                    "collectionViewUrl": "https://music.apple.com/us/album/parachutes/456",
                }
            ]
        }

        with patch.object(metadata_tool, "search_songs", return_value=payload):
            result = fetch_music_metadata("Yellow", artist="Coldplay", album="Parachutes", limit=2)

        self.assertEqual(
            result,
            [
                {
                    "track_id": 123,
                    "collection_id": 456,
                    "title": "Yellow",
                    "artist": "Coldplay",
                    "album": "Parachutes",
                    "release_date": "2000-06-26T07:00:00Z",
                    "duration_ms": 266000,
                    "track_explicitness": "notExplicit",
                    "is_explicit": False,
                    "track_number": 5,
                    "disc_number": 1,
                    "primary_genre_name": "Alternative",
                    "artwork_url": "https://example.com/art.jpg",
                    "preview_url": "https://example.com/preview.m4a",
                    "track_view_url": "https://music.apple.com/us/song/yellow/123",
                    "collection_view_url": "https://music.apple.com/us/album/parachutes/456",
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
            model=DEFAULT_OLLAMA_MODEL,
            host="http://127.0.0.1:11434",
            temperature=0,
        )
        mock_fetch.assert_called_once_with(
            "Yellow",
            artist="Coldplay",
            limit=4,
            config=None,
        )

    def test_build_fallback_tag_metadata_uses_request_and_description(self) -> None:
        song_request = SongRequest(
            song_name="Resham Firiri",
            artist=None,
            album=None,
            format="m4a",
            search_query="Resham Firiri official audio",
        )
        metadata_request = MetadataLookupRequest(
            song_name="Resham Firiri",
            artist="Kutama Band",
            reasoning="Search results strongly indicate the same artist and title.",
        )
        selected_result = {
            "id": "abc123",
            "title": "Kutama Band - Resham Firiri (Lyrics)",
            "uploader": "Nepali Classics",
            "description": "From the album Folk Favorites",
            "duration_seconds": 200,
            "webpage_url": "https://www.youtube.com/watch?v=abc123",
            "view_count": 50_000,
        }

        result = metadata_tool.build_fallback_tag_metadata(
            song_request,
            metadata_request,
            selected_result=selected_result,
        )

        self.assertEqual(
            result,
            TagMetadata(
                title="Resham Firiri",
                artist="Kutama Band",
                album="Folk Favorites",
                artwork_url=None,
            ),
        )

    def test_fetch_lyrics_uses_tag_metadata(self) -> None:
        metadata = TagMetadata(
            title="Yellow",
            artist="Coldplay",
            album="Parachutes",
            artwork_url=None,
        )

        with patch.object(
            lyrics_tool,
            "lookup_lyrics",
            return_value=LyricsResult(
                plain_lyrics="Look at the stars",
                source="lrclib",
                found=True,
            ),
        ) as mock_lookup:
            result = fetch_lyrics(metadata, duration_seconds=266)

        self.assertEqual(result.plain_lyrics, "Look at the stars")
        mock_lookup.assert_called_once_with(
            "Yellow",
            artist="Coldplay",
            album="Parachutes",
            duration_seconds=266,
            config=None,
        )


if __name__ == "__main__":
    unittest.main()
