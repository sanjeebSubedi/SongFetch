import json
import unittest
from unittest.mock import patch

from src.providers.ollama import DEFAULT_OLLAMA_MODEL
from src import (
    ITunesConfig,
    LRCLibConfig,
    LyricsResult,
    MetadataLookupRequest,
    PlaylistTrack,
    SongRequest,
    SpotifyConfig,
    TagMetadata,
    fetch_lyrics,
    fetch_metadata_from_request,
    fetch_metadata_from_search_results,
    fetch_music_metadata,
    fetch_spotify_metadata,
    import_spotify_playlist_tracks,
)
from src.providers import itunes, lrclib, spotify
from src.tools import metadata as metadata_tool
from src.tools import lyrics as lyrics_tool
from src.tools import spotify as spotify_tool


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


class FakeHeaders(dict):
    def get_content_type(self):
        value = self.get("Content-Type", "application/json")
        return value.split(";", maxsplit=1)[0]


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

    def test_lookup_lyrics_returns_none_on_timeout(self) -> None:
        config = LRCLibConfig(base_url="https://lrclib.net/api")

        with patch.object(
            lrclib.request,
            "urlopen",
            side_effect=TimeoutError("timed out"),
        ):
            result = lrclib.lookup_lyrics("Yellow", artist="Coldplay", config=config)

        self.assertIsNone(result)


class SpotifyProviderTests(unittest.TestCase):
    def test_search_tracks_normalizes_scraped_track_results(self) -> None:
        class FakeSpotifyClient:
            def get_track_info(self, _url: str) -> dict[str, object]:
                return {
                    "id": "spotify-track-1",
                    "name": "Yellow",
                    "artists": [{"name": "Coldplay"}],
                    "album": {
                        "id": "spotify-album-1",
                        "name": "Parachutes",
                        "release_date": "2000-07-10",
                        "images": [
                            {"height": 300, "url": "https://example.com/small.jpg"},
                            {"height": 640, "url": "https://example.com/large.jpg"},
                        ],
                        "external_urls": {
                            "spotify": "https://open.spotify.com/album/spotify-album-1"
                        },
                    },
                    "duration_ms": 266000,
                    "explicit": False,
                    "track_number": 5,
                    "disc_number": 1,
                    "preview_url": "https://example.com/preview.mp3",
                    "external_urls": {
                        "spotify": "https://open.spotify.com/track/spotify-track-1"
                    },
                }

            def close(self) -> None:
                return None

        config = SpotifyConfig(browser_name="chrome", headless=True)

        with patch.object(
            spotify,
            "_discover_track_urls",
            return_value=["https://open.spotify.com/track/spotify-track-1"],
        ):
            with patch.object(
                spotify,
                "_build_track_client",
                return_value=FakeSpotifyClient(),
            ):
                result = spotify.search_tracks(
                    "Yellow",
                    artist="Coldplay",
                    limit=3,
                    config=config,
                )

        self.assertEqual(
            result,
            [
                {
                    "provider": "spotify",
                    "provider_track_id": "spotify-track-1",
                    "provider_collection_id": "spotify-album-1",
                    "title": "Yellow",
                    "artist": "Coldplay",
                    "album": "Parachutes",
                    "release_date": "2000-07-10",
                    "duration_ms": 266000,
                    "explicitness": "notExplicit",
                    "is_explicit": False,
                    "track_number": 5,
                    "disc_number": 1,
                    "genre": None,
                    "artwork_url": "https://example.com/large.jpg",
                    "preview_url": "https://example.com/preview.mp3",
                    "track_view_url": "https://open.spotify.com/track/spotify-track-1",
                    "collection_view_url": "https://open.spotify.com/album/spotify-album-1",
                }
            ],
        )

    def test_search_tracks_returns_empty_when_browser_type_is_not_supported(self) -> None:
        result = spotify.search_tracks(
            "Yellow",
            artist="Coldplay",
            config=SpotifyConfig(browser_type="requests"),
        )
        self.assertEqual(result, [])

    def test_search_tracks_returns_empty_when_discovery_raises(self) -> None:
        with patch.object(
            spotify,
            "_discover_track_urls",
            side_effect=RuntimeError("browser crashed"),
        ):
            result = spotify.search_tracks("Yellow", artist="Coldplay", limit=3)

        self.assertEqual(result, [])

    def test_fetch_public_playlist_preserves_duplicates_and_order(self) -> None:
        config = SpotifyConfig(browser_name="chrome", headless=True)
        rows = [
            {
                "position": 1,
                "title": "Song One",
                "artists": ["Artist One"],
                "album": "Album One",
                "track_url": "/track/track-1",
                "album_url": "/album/album-1",
            },
            {
                "position": 2,
                "title": "Song One",
                "artists": ["Artist One"],
                "album": "Album One",
                "track_url": "/track/track-1",
                "album_url": "/album/album-1",
            },
        ]

        with patch.object(
            spotify,
            "_scrape_playlist_rows",
            return_value=("Road Trip", rows),
        ):
            result = spotify.fetch_public_playlist(
                "https://open.spotify.com/playlist/playlist-1",
                config=config,
            )

        self.assertEqual(result["playlist_id"], "playlist-1")
        self.assertEqual(result["name"], "Road Trip")
        self.assertEqual(len(result["tracks"]), 2)
        self.assertEqual(result["tracks"][0].title, "Song One")
        self.assertEqual(result["tracks"][1].title, "Song One")
        self.assertEqual(result["tracks"][0].provider_track_id, "track-1")
        self.assertEqual(result["tracks"][1].provider_track_id, "track-1")


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
                    "provider": "itunes",
                    "provider_track_id": "123",
                    "provider_collection_id": "456",
                    "title": "Yellow",
                    "artist": "Coldplay",
                    "album": "Parachutes",
                    "release_date": "2000-06-26T07:00:00Z",
                    "duration_ms": 266000,
                    "explicitness": "notExplicit",
                    "is_explicit": False,
                    "track_number": 5,
                    "disc_number": 1,
                    "genre": "Alternative",
                    "artwork_url": "https://example.com/art.jpg",
                    "preview_url": "https://example.com/preview.m4a",
                    "track_view_url": "https://music.apple.com/us/song/yellow/123",
                    "collection_view_url": "https://music.apple.com/us/album/parachutes/456",
                }
            ],
        )

    def test_fetch_spotify_metadata_uses_spotify_search(self) -> None:
        spotify_matches = [
            {
                "provider": "spotify",
                "provider_track_id": "spotify-track-1",
                "provider_collection_id": "spotify-album-1",
                "title": "Yellow",
                "artist": "Coldplay",
                "album": "Parachutes",
                "release_date": "2000-07-10",
                "duration_ms": 266000,
                "explicitness": "notExplicit",
                "is_explicit": False,
                "track_number": 5,
                "disc_number": 1,
                    "genre": None,
                "artwork_url": "https://example.com/large.jpg",
                "preview_url": None,
                "track_view_url": "https://open.spotify.com/track/spotify-track-1",
                "collection_view_url": "https://open.spotify.com/album/spotify-album-1",
            }
        ]

        with patch.object(metadata_tool, "search_spotify_tracks", return_value=spotify_matches) as mock_search:
            result = fetch_spotify_metadata("Yellow", artist="Coldplay", limit=2)

        self.assertEqual(result, spotify_matches)
        mock_search.assert_called_once()

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

    def test_import_spotify_playlist_tracks_returns_normalized_tracks(self) -> None:
        playlist = {
            "playlist_id": "playlist-1",
            "name": "Road Trip",
            "spotify_url": "https://open.spotify.com/playlist/playlist-1",
            "tracks": [
                PlaylistTrack(
                    provider="spotify",
                    provider_track_id="track-1",
                    title="Song One",
                    artist="Artist One",
                    album="Album One",
                    artwork_url="https://example.com/1.jpg",
                    spotify_track_url="https://open.spotify.com/track/track-1",
                )
            ],
        }

        with patch.object(spotify_tool, "fetch_public_playlist", return_value=playlist):
            result = import_spotify_playlist_tracks("playlist-1")

        self.assertEqual(result["playlist_id"], "playlist-1")
        self.assertEqual(result["name"], "Road Trip")
        self.assertEqual(len(result["tracks"]), 1)
        self.assertEqual(result["tracks"][0].title, "Song One")

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
