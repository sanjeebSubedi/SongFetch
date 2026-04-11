import json
import unittest
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

import main as app_main
from src import (
    DownloadAudioSelection,
    LyricsResult,
    MetadataLookupRequest,
    MetadataSelection,
    PlaylistTrack,
    SongRequest,
)


class MainTests(unittest.TestCase):
    def test_run_pipeline_returns_staged_payload(self) -> None:
        song_request = SongRequest(
            song_name="Yellow",
            artist="Coldplay",
            album=None,
            format="m4a",
            search_query="Coldplay Yellow official audio",
        )
        search_results = [
            {
                "id": "abc123",
                "title": "Coldplay - Yellow",
                "uploader": "Coldplay",
                "duration_seconds": 269,
                "webpage_url": "https://www.youtube.com/watch?v=abc123",
                "view_count": 42,
            }
        ]
        metadata_lookup_request = MetadataLookupRequest(
            song_name="Yellow",
            artist="Coldplay",
            reasoning="Coldplay is the clearest consensus across the top YouTube results.",
        )
        metadata_matches = [
            {
                "provider": "itunes",
                "provider_track_id": "123",
                "provider_collection_id": "456",
                "title": "Yellow",
                "artist": "Coldplay",
                "album": "Parachutes",
                "release_date": "2000-06-26T07:00:00Z",
                "duration_ms": 266000,
                "explicitness": "explicit",
                "is_explicit": True,
                "track_number": 5,
                "disc_number": 1,
                "genre": "Alternative",
                "artwork_url": "https://example.com/art.jpg",
                "preview_url": "https://example.com/preview.m4a",
                "track_view_url": "https://music.apple.com/us/song/yellow/123",
                "collection_view_url": "https://music.apple.com/us/album/parachutes/456",
            }
        ]
        selected_metadata = MetadataSelection(
            provider="itunes",
            provider_track_id="123",
            provider_collection_id="456",
            title="Yellow",
            artist="Coldplay",
            album="Parachutes",
            genre="Alternative",
            track_number=5,
            disc_number=1,
            artwork_url="https://example.com/art.jpg",
            duration_ms=266000,
            is_explicit=True,
            reason="Earliest studio album match with valid length and no disambiguation noise.",
        )
        selected_download = DownloadAudioSelection.model_validate(
            {
                "reasoning": "Candidate #1 matches duration and is from an official source.",
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
        download_result = {
            "id": "abc123",
            "title": "Coldplay - Yellow",
            "source_url": "https://www.youtube.com/watch?v=abc123",
            "output_path": "downloads/Coldplay - Yellow.m4a",
            "audio_format": "m4a",
        }

        with patch.object(app_main, "build_song_request", return_value=song_request):
            with patch.object(app_main, "search_song_audio", return_value=search_results):
                with patch.object(
                    app_main,
                    "build_metadata_lookup_request",
                    return_value=metadata_lookup_request,
                ):
                    with patch.object(
                        app_main,
                        "fetch_music_metadata",
                        return_value=metadata_matches,
                    ) as mock_fetch:
                        with patch.object(
                            app_main,
                            "select_metadata_match",
                            return_value=selected_metadata,
                        ) as mock_select:
                            with patch.object(
                                app_main,
                                "select_download_audio_request",
                                return_value=selected_download,
                            ) as mock_download_select:
                                with patch.object(
                                    app_main,
                                    "fetch_lyrics",
                                    return_value=LyricsResult(
                                        plain_lyrics="Look at the stars",
                                        source="lrclib",
                                        found=True,
                                        synced_available=True,
                                        synced_used=False,
                                    ),
                                ) as mock_fetch_lyrics:
                                    with patch.object(
                                        app_main,
                                        "download_song_audio",
                                        return_value=download_result,
                                    ) as mock_download:
                                        with patch.object(
                                            app_main,
                                            "embed_selected_metadata",
                                            return_value={
                                                "path": "downloads/Coldplay - Yellow.m4a",
                                                "container": "m4a",
                                                "artwork_embedded": True,
                                                "lyrics_embedded": True,
                                            },
                                        ) as mock_tag:
                                            result = app_main.run_pipeline(
                                                "download Yellow by Coldplay",
                                                search_limit=3,
                                                metadata_limit=4,
                                            )

        self.assertEqual(result["song_request"], song_request.model_dump())
        self.assertEqual(result["search_results"], search_results)
        self.assertEqual(
            result["metadata_lookup_request"],
            metadata_lookup_request.model_dump(),
        )
        self.assertEqual(result["metadata_matches"], metadata_matches)
        self.assertEqual(result["metadata_source"], "itunes")
        self.assertEqual(result["download_selection_source"], "metadata_selector")
        self.assertEqual(result["selected_metadata"], selected_metadata.model_dump())
        self.assertEqual(result["selected_download"], selected_download.model_dump())
        self.assertEqual(result["download_result"], download_result)
        self.assertEqual(
            result["lyrics_result"],
            {
                "found": True,
                "source": "lrclib",
                "synced_available": True,
                "synced_used": False,
                "lyrics_embedded": True,
            },
        )
        self.assertEqual(
            result["tagging_result"],
            {
                "path": "downloads/Coldplay - Yellow.m4a",
                "container": "m4a",
                "artwork_embedded": True,
                "lyrics_embedded": True,
            },
        )
        mock_fetch.assert_called_once()
        mock_select.assert_called_once()
        mock_download_select.assert_called_once()
        mock_fetch_lyrics.assert_called_once()
        mock_download.assert_called_once_with(
            "https://www.youtube.com/watch?v=abc123",
            audio_format="m4a",
            filename="Coldplay - Yellow",
        )
        mock_tag.assert_called_once_with(
            "downloads/Coldplay - Yellow.m4a",
            selected_metadata,
            lyrics="Look at the stars",
        )
        self.assertEqual(mock_fetch.call_args.args[0], "Yellow")
        self.assertEqual(mock_fetch.call_args.kwargs["artist"], "Coldplay")
        self.assertEqual(mock_fetch.call_args.kwargs["limit"], 4)

    def test_run_pipeline_uses_spotify_metadata_when_itunes_has_no_matches(self) -> None:
        song_request = SongRequest(
            song_name="Yellow",
            artist="Coldplay",
            album=None,
            format="m4a",
            search_query="Coldplay Yellow official audio",
        )
        search_results = [
            {
                "id": "abc123",
                "title": "Coldplay - Yellow",
                "uploader": "Coldplay",
                "description": None,
                "duration_seconds": 269,
                "webpage_url": "https://www.youtube.com/watch?v=abc123",
                "view_count": 42,
            }
        ]
        metadata_lookup_request = MetadataLookupRequest(
            song_name="Yellow",
            artist="Coldplay",
            reasoning="Coldplay is the clearest consensus across the top YouTube results.",
        )
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
                "artwork_url": "https://example.com/spotify-art.jpg",
                "preview_url": None,
                "track_view_url": "https://open.spotify.com/track/spotify-track-1",
                "collection_view_url": "https://open.spotify.com/album/spotify-album-1",
            }
        ]
        selected_metadata = MetadataSelection(
            provider="spotify",
            provider_track_id="spotify-track-1",
            provider_collection_id="spotify-album-1",
            title="Yellow",
            artist="Coldplay",
            album="Parachutes",
            genre=None,
            track_number=5,
            disc_number=1,
            artwork_url="https://example.com/spotify-art.jpg",
            duration_ms=266000,
            is_explicit=False,
            reason="Spotify fallback metadata matched title, artist, and duration.",
        )
        selected_download = DownloadAudioSelection.model_validate(
            {
                "reasoning": "Candidate #1 matches duration and is from an official source.",
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
        download_result = {
            "id": "abc123",
            "title": "Coldplay - Yellow",
            "source_url": "https://www.youtube.com/watch?v=abc123",
            "output_path": "downloads/Coldplay - Yellow.m4a",
            "audio_format": "m4a",
        }

        with patch.object(app_main, "build_song_request", return_value=song_request):
            with patch.object(app_main, "search_song_audio", return_value=search_results):
                with patch.object(
                    app_main,
                    "build_metadata_lookup_request",
                    return_value=metadata_lookup_request,
                ):
                    with patch.object(app_main, "fetch_music_metadata", return_value=[]):
                        with patch.object(app_main, "fetch_spotify_metadata", return_value=spotify_matches) as mock_spotify:
                            with patch.object(
                                app_main,
                                "select_metadata_match",
                                return_value=selected_metadata,
                            ):
                                with patch.object(
                                    app_main,
                                    "select_download_audio_request",
                                    return_value=selected_download,
                                ):
                                    with patch.object(
                                        app_main,
                                        "fetch_lyrics",
                                        return_value=None,
                                    ):
                                        with patch.object(
                                            app_main,
                                            "download_song_audio",
                                            return_value=download_result,
                                        ):
                                            with patch.object(
                                                app_main,
                                                "embed_selected_metadata",
                                                return_value={
                                                    "path": "downloads/Coldplay - Yellow.m4a",
                                                    "container": "m4a",
                                                    "artwork_embedded": True,
                                                    "lyrics_embedded": False,
                                                },
                                            ):
                                                result = app_main.run_pipeline("download Yellow by Coldplay")

        self.assertEqual(result["metadata_source"], "spotify")
        self.assertEqual(result["download_selection_source"], "metadata_selector")
        self.assertEqual(result["metadata_matches"], spotify_matches)
        mock_spotify.assert_called_once()

    def test_run_pipeline_falls_back_when_metadata_download_selector_fails(self) -> None:
        song_request = SongRequest(
            song_name="Yellow",
            artist="Coldplay",
            album=None,
            format="m4a",
            search_query="Coldplay Yellow official audio",
        )
        search_results = [
            {
                "id": "abc123",
                "title": "Coldplay - Yellow",
                "uploader": "Coldplay",
                "description": None,
                "duration_seconds": 269,
                "webpage_url": "https://www.youtube.com/watch?v=abc123",
                "view_count": 42,
            }
        ]
        metadata_lookup_request = MetadataLookupRequest(
            song_name="Yellow",
            artist="Coldplay",
            reasoning="Coldplay is the clearest consensus across the top YouTube results.",
        )
        metadata_matches = [
            {
                "provider": "itunes",
                "provider_track_id": "123",
                "provider_collection_id": "456",
                "title": "Yellow",
                "artist": "Coldplay",
                "album": "Parachutes",
                "release_date": "2000-06-26T07:00:00Z",
                "duration_ms": 266000,
                "explicitness": "explicit",
                "is_explicit": True,
                "track_number": 5,
                "disc_number": 1,
                "genre": "Alternative",
                "artwork_url": "https://example.com/art.jpg",
                "preview_url": None,
                "track_view_url": "https://music.apple.com/us/song/yellow/123",
                "collection_view_url": "https://music.apple.com/us/album/parachutes/456",
            }
        ]
        selected_metadata = MetadataSelection(
            provider="itunes",
            provider_track_id="123",
            provider_collection_id="456",
            title="Yellow",
            artist="Coldplay",
            album="Parachutes",
            genre="Alternative",
            track_number=5,
            disc_number=1,
            artwork_url="https://example.com/art.jpg",
            duration_ms=266000,
            is_explicit=True,
            reason="Earliest studio album match with valid length and no disambiguation noise.",
        )
        fallback_download = DownloadAudioSelection.model_validate(
            {
                "reasoning": "Selected a best-effort YouTube fallback.",
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
        download_result = {
            "id": "abc123",
            "title": "Coldplay - Yellow",
            "source_url": "https://www.youtube.com/watch?v=abc123",
            "output_path": "downloads/Coldplay - Yellow.m4a",
            "audio_format": "m4a",
        }

        with patch.object(app_main, "build_song_request", return_value=song_request):
            with patch.object(app_main, "search_song_audio", return_value=search_results):
                with patch.object(
                    app_main,
                    "build_metadata_lookup_request",
                    return_value=metadata_lookup_request,
                ):
                    with patch.object(
                        app_main,
                        "fetch_music_metadata",
                        return_value=metadata_matches,
                    ):
                        with patch.object(
                            app_main,
                            "select_metadata_match",
                            return_value=selected_metadata,
                        ):
                            with patch.object(
                                app_main,
                                "select_download_audio_request",
                                side_effect=RuntimeError(
                                    "No valid candidate within threshold"
                                ),
                            ):
                                with patch.object(
                                    app_main,
                                    "select_fallback_download_audio_request",
                                    return_value=fallback_download,
                                ) as mock_select_fallback:
                                    with patch.object(
                                        app_main,
                                        "fetch_lyrics",
                                        return_value=None,
                                    ):
                                        with patch.object(
                                            app_main,
                                            "download_song_audio",
                                            return_value=download_result,
                                        ):
                                            with patch.object(
                                                app_main,
                                                "embed_selected_metadata",
                                                return_value={
                                                    "path": "downloads/Coldplay - Yellow.m4a",
                                                    "container": "m4a",
                                                    "artwork_embedded": True,
                                                    "lyrics_embedded": False,
                                                },
                                            ):
                                                result = app_main.run_pipeline(
                                                    "download Yellow by Coldplay"
                                                )

        self.assertEqual(result["metadata_source"], "itunes")
        self.assertEqual(result["download_selection_source"], "fallback_selector")
        self.assertEqual(result["selected_metadata"], selected_metadata.model_dump())
        self.assertEqual(result["selected_download"], fallback_download.model_dump())
        mock_select_fallback.assert_called_once_with(
            "download Yellow by Coldplay",
            search_results,
            requested_format="m4a",
            song_name="Yellow",
            artist="Coldplay",
        )

    def test_run_pipeline_continues_tagging_when_lyrics_lookup_raises(self) -> None:
        song_request = SongRequest(
            song_name="Yellow",
            artist="Coldplay",
            album=None,
            format="m4a",
            search_query="Coldplay Yellow official audio",
        )
        search_results = [
            {
                "id": "abc123",
                "title": "Coldplay - Yellow",
                "uploader": "Coldplay",
                "description": None,
                "duration_seconds": 269,
                "webpage_url": "https://www.youtube.com/watch?v=abc123",
                "view_count": 42,
            }
        ]
        metadata_lookup_request = MetadataLookupRequest(
            song_name="Yellow",
            artist="Coldplay",
            reasoning="Coldplay is the clearest consensus across the top YouTube results.",
        )
        metadata_matches = [
            {
                "provider": "itunes",
                "provider_track_id": "123",
                "provider_collection_id": "456",
                "title": "Yellow",
                "artist": "Coldplay",
                "album": "Parachutes",
                "release_date": "2000-06-26T07:00:00Z",
                "duration_ms": 266000,
                "explicitness": "explicit",
                "is_explicit": True,
                "track_number": 5,
                "disc_number": 1,
                "genre": "Alternative",
                "artwork_url": "https://example.com/art.jpg",
                "preview_url": None,
                "track_view_url": "https://music.apple.com/us/song/yellow/123",
                "collection_view_url": "https://music.apple.com/us/album/parachutes/456",
            }
        ]
        selected_metadata = MetadataSelection(
            provider="itunes",
            provider_track_id="123",
            provider_collection_id="456",
            title="Yellow",
            artist="Coldplay",
            album="Parachutes",
            genre="Alternative",
            track_number=5,
            disc_number=1,
            artwork_url="https://example.com/art.jpg",
            duration_ms=266000,
            is_explicit=True,
            reason="Earliest studio album match with valid length and no disambiguation noise.",
        )
        selected_download = DownloadAudioSelection.model_validate(
            {
                "reasoning": "Candidate #1 matches duration and is from an official source.",
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
        download_result = {
            "id": "abc123",
            "title": "Coldplay - Yellow",
            "source_url": "https://www.youtube.com/watch?v=abc123",
            "output_path": "downloads/Coldplay - Yellow.m4a",
            "audio_format": "m4a",
        }

        with patch.object(app_main, "build_song_request", return_value=song_request):
            with patch.object(app_main, "search_song_audio", return_value=search_results):
                with patch.object(
                    app_main,
                    "build_metadata_lookup_request",
                    return_value=metadata_lookup_request,
                ):
                    with patch.object(
                        app_main,
                        "fetch_music_metadata",
                        return_value=metadata_matches,
                    ):
                        with patch.object(
                            app_main,
                            "select_metadata_match",
                            return_value=selected_metadata,
                        ):
                            with patch.object(
                                app_main,
                                "select_download_audio_request",
                                return_value=selected_download,
                            ):
                                with patch.object(
                                    app_main,
                                    "fetch_lyrics",
                                    side_effect=TimeoutError("timed out"),
                                ) as mock_fetch_lyrics:
                                    with patch.object(
                                        app_main,
                                        "download_song_audio",
                                        return_value=download_result,
                                    ):
                                        with patch.object(
                                            app_main,
                                            "embed_selected_metadata",
                                            return_value={
                                                "path": "downloads/Coldplay - Yellow.m4a",
                                                "container": "m4a",
                                                "artwork_embedded": True,
                                                "lyrics_embedded": False,
                                            },
                                        ) as mock_tag:
                                            result = app_main.run_pipeline(
                                                "download Yellow by Coldplay"
                                            )

        self.assertEqual(result["download_result"], download_result)
        self.assertEqual(
            result["lyrics_result"],
            {
                "found": False,
                "source": "lrclib",
                "lyrics_embedded": False,
            },
        )
        self.assertEqual(
            result["tagging_result"],
            {
                "path": "downloads/Coldplay - Yellow.m4a",
                "container": "m4a",
                "artwork_embedded": True,
                "lyrics_embedded": False,
            },
        )
        mock_fetch_lyrics.assert_called_once()
        mock_tag.assert_called_once_with(
            "downloads/Coldplay - Yellow.m4a",
            selected_metadata,
            lyrics=None,
        )

    def test_run_pipeline_requires_search_results(self) -> None:
        song_request = SongRequest(
            song_name="Yellow",
            artist="Coldplay",
            album=None,
            format="m4a",
            search_query="Coldplay Yellow official audio",
        )

        with patch.object(app_main, "build_song_request", return_value=song_request):
            with patch.object(app_main, "search_song_audio", return_value=[]):
                with self.assertRaises(RuntimeError):
                    app_main.run_pipeline("download Yellow by Coldplay")

    def test_run_pipeline_falls_back_when_metadata_matches_are_missing(self) -> None:
        song_request = SongRequest(
            song_name="Resham Firiri",
            artist=None,
            album=None,
            format="m4a",
            search_query="Resham Firiri official audio",
        )
        search_results = [
            {
                "id": "abc123",
                "title": "Resham Firiri (Lyrics)",
                "uploader": "Nepali Classics",
                "description": "From the album Folk Favorites",
                "duration_seconds": 200,
                "webpage_url": "https://www.youtube.com/watch?v=abc123",
                "view_count": 50000,
            }
        ]
        metadata_lookup_request = MetadataLookupRequest(
            song_name="Resham Firiri",
            artist="Kutama Band",
            reasoning="Search results consistently point to the same song name.",
        )
        fallback_download = DownloadAudioSelection.model_validate(
            {
                "reasoning": "Selected the lyrics upload because it has strong views.",
                "tool_call": {
                    "tool": "download_audio",
                    "parameters": {
                        "url": "https://www.youtube.com/watch?v=abc123",
                        "format": "m4a",
                        "filename": "Kutama Band - Resham Firiri",
                    },
                },
            }
        )
        fallback_tag_metadata = SimpleNamespace(
            title="Resham Firiri",
            artist="Kutama Band",
            album="Folk Favorites",
            artwork_url=None,
        )
        download_result = {
            "id": "abc123",
            "title": "Resham Firiri (Lyrics)",
            "source_url": "https://www.youtube.com/watch?v=abc123",
            "output_path": "downloads/Kutama Band - Resham Firiri.m4a",
            "audio_format": "m4a",
        }

        with patch.object(app_main, "build_song_request", return_value=song_request):
            with patch.object(app_main, "search_song_audio", return_value=search_results):
                with patch.object(
                    app_main,
                    "build_metadata_lookup_request",
                    return_value=metadata_lookup_request,
                ):
                    with patch.object(
                        app_main,
                        "fetch_music_metadata",
                        return_value=[],
                    ) as mock_fetch:
                        with patch.object(
                            app_main,
                            "fetch_spotify_metadata",
                            return_value=[],
                        ) as mock_fetch_spotify:
                            with patch.object(
                                app_main,
                                "select_fallback_download_audio_request",
                                return_value=fallback_download,
                            ) as mock_select_fallback:
                                with patch.object(
                                    app_main,
                                    "fetch_lyrics",
                                    return_value=LyricsResult(
                                        plain_lyrics="Resham firiri",
                                        source="lrclib",
                                        found=True,
                                        synced_available=False,
                                        synced_used=False,
                                    ),
                                ) as mock_fetch_lyrics:
                                    with patch.object(
                                        app_main,
                                        "download_song_audio",
                                        return_value=download_result,
                                    ) as mock_download:
                                        with patch.object(
                                            app_main,
                                            "build_fallback_tag_metadata",
                                            return_value=fallback_tag_metadata,
                                        ) as mock_build_tag:
                                            with patch.object(
                                                app_main,
                                                "embed_selected_metadata",
                                                return_value={
                                                    "path": "downloads/Kutama Band - Resham Firiri.m4a",
                                                    "container": "m4a",
                                                    "artwork_embedded": False,
                                                    "lyrics_embedded": True,
                                                },
                                            ) as mock_tag:
                                                result = app_main.run_pipeline(
                                                    "download Resham Firiri",
                                                    search_limit=3,
                                                    metadata_limit=4,
                                                )

        self.assertEqual(result["metadata_matches"], [])
        self.assertEqual(result["metadata_source"], "fallback")
        self.assertEqual(result["download_selection_source"], "fallback_selector")
        self.assertIsNone(result["selected_metadata"])
        self.assertEqual(result["selected_download"], fallback_download.model_dump())
        self.assertEqual(result["download_result"], download_result)
        self.assertEqual(
            result["lyrics_result"],
            {
                "found": True,
                "source": "lrclib",
                "synced_available": False,
                "synced_used": False,
                "lyrics_embedded": True,
            },
        )
        self.assertEqual(
            result["tagging_result"],
            {
                "path": "downloads/Kutama Band - Resham Firiri.m4a",
                "container": "m4a",
                "artwork_embedded": False,
                "lyrics_embedded": True,
            },
        )
        mock_fetch.assert_called_once()
        mock_fetch_spotify.assert_called_once_with(
            "Resham Firiri",
            artist="Kutama Band",
            limit=4,
            config=app_main.SpotifyConfig(),
        )
        mock_select_fallback.assert_called_once()
        mock_fetch_lyrics.assert_called_once()
        mock_download.assert_called_once_with(
            "https://www.youtube.com/watch?v=abc123",
            audio_format="m4a",
            filename="Kutama Band - Resham Firiri",
        )
        mock_build_tag.assert_called_once_with(
            song_request,
            metadata_lookup_request,
            selected_result=search_results[0],
        )
        mock_tag.assert_called_once_with(
            "downloads/Kutama Band - Resham Firiri.m4a",
            fallback_tag_metadata,
            lyrics="Resham firiri",
        )

    def test_main_prints_pipeline_json(self) -> None:
        stdout = StringIO()
        payload = {
            "user_input": "download Yellow by Coldplay",
            "song_request": {
                "song_name": "Yellow",
                "artist": "Coldplay",
                "album": None,
                "format": "m4a",
                "search_query": "Coldplay Yellow official audio",
            },
            "search_results": [],
            "metadata_lookup_request": {
                "song_name": "Yellow",
                "artist": "Coldplay",
                "reasoning": "Coldplay is the clearest match.",
            },
            "metadata_matches": [],
            "metadata_source": "fallback",
            "download_selection_source": None,
            "selected_metadata": None,
            "selected_download": None,
            "download_result": None,
            "lyrics_result": {
                "found": False,
                "source": "lrclib",
                "lyrics_embedded": False,
            },
            "tagging_result": None,
        }

        with patch.object(app_main, "run_pipeline", return_value=payload):
            with patch("sys.stdout", stdout):
                exit_code = app_main.main(["download", "Yellow", "by", "Coldplay"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue()), payload)

    def test_run_spotify_playlist_pipeline_runs_tracks_in_order(self) -> None:
        playlist_tracks = [
            PlaylistTrack(
                provider="spotify",
                provider_track_id="track-1",
                title="Song One",
                artist="Artist One",
                album="Album One",
                artwork_url="https://example.com/1.jpg",
                spotify_track_url="https://open.spotify.com/track/track-1",
            ),
            PlaylistTrack(
                provider="spotify",
                provider_track_id="track-2",
                title="Song Two",
                artist="Artist Two",
                album="Album Two",
                artwork_url="https://example.com/2.jpg",
                spotify_track_url="https://open.spotify.com/track/track-2",
            ),
        ]
        playlist_payload = {
            "playlist_id": "playlist-1",
            "name": "Road Trip",
            "spotify_url": "https://open.spotify.com/playlist/playlist-1",
            "tracks": playlist_tracks,
        }
        per_track_results = [
            {
                "metadata_source": "itunes",
                "download_result": {"output_path": "downloads/Artist One - Song One.m4a"},
            },
            {
                "metadata_source": "spotify",
                "download_result": {"output_path": "downloads/Artist Two - Song Two.m4a"},
            },
        ]

        with patch.object(
            app_main,
            "import_spotify_playlist_tracks",
            return_value=playlist_payload,
        ):
            with patch.object(
                app_main,
                "run_pipeline",
                side_effect=per_track_results,
            ) as mock_run_pipeline:
                result = app_main.run_spotify_playlist_pipeline("playlist-1")

        self.assertEqual(result["playlist"]["playlist_id"], "playlist-1")
        self.assertEqual(result["summary"]["total"], 2)
        self.assertEqual(result["summary"]["downloaded"], 2)
        self.assertEqual(result["summary"]["metadata_from_itunes"], 1)
        self.assertEqual(result["summary"]["metadata_from_spotify"], 1)
        self.assertEqual(result["summary"]["fallback_only"], 0)
        self.assertEqual(result["tracks"][0]["playlist_track"]["title"], "Song One")
        self.assertEqual(mock_run_pipeline.call_args_list[0].args[0], 'download "Song One" by Artist One from the album Album One')
        self.assertEqual(mock_run_pipeline.call_args_list[1].args[0], 'download "Song Two" by Artist Two from the album Album Two')

    def test_run_spotify_playlist_pipeline_records_failures_and_continues(self) -> None:
        playlist_tracks = [
            PlaylistTrack(
                provider="spotify",
                provider_track_id="track-1",
                title="Song One",
                artist="Artist One",
                album=None,
                artwork_url=None,
                spotify_track_url="https://open.spotify.com/track/track-1",
            ),
            PlaylistTrack(
                provider="spotify",
                provider_track_id="track-2",
                title="Song Two",
                artist="Artist Two",
                album=None,
                artwork_url=None,
                spotify_track_url="https://open.spotify.com/track/track-2",
            ),
        ]
        playlist_payload = {
            "playlist_id": "playlist-1",
            "name": "Road Trip",
            "spotify_url": "https://open.spotify.com/playlist/playlist-1",
            "tracks": playlist_tracks,
        }

        with patch.object(
            app_main,
            "import_spotify_playlist_tracks",
            return_value=playlist_payload,
        ):
            with patch.object(
                app_main,
                "run_pipeline",
                side_effect=[
                    RuntimeError("metadata lookup blew up"),
                    {
                        "metadata_source": "fallback",
                        "download_result": {
                            "output_path": "downloads/Artist Two - Song Two.m4a"
                        },
                    },
                ],
            ) as mock_run_pipeline:
                result = app_main.run_spotify_playlist_pipeline("playlist-1")

        self.assertEqual(result["summary"]["total"], 2)
        self.assertEqual(result["summary"]["downloaded"], 1)
        self.assertEqual(result["summary"]["failed"], 1)
        self.assertEqual(result["summary"]["fallback_only"], 1)
        self.assertEqual(result["tracks"][0]["error"], "metadata lookup blew up")
        self.assertIsNone(result["tracks"][0]["result"])
        self.assertEqual(result["tracks"][1]["error"], None)
        self.assertEqual(mock_run_pipeline.call_count, 2)


if __name__ == "__main__":
    unittest.main()
