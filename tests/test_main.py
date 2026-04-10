import json
import unittest
from io import StringIO
from unittest.mock import patch

import main as app_main
from src import DownloadAudioSelection, MetadataLookupRequest, MetadataSelection, SongRequest


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
        selected_metadata = MetadataSelection(
            recording_id="recording-1",
            release_group_id="release-group-1",
            title="Yellow",
            artist="Coldplay",
            album="Parachutes",
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
                                    "download_song_audio",
                                    return_value=download_result,
                                ) as mock_download:
                                    with patch.object(
                                        app_main,
                                        "embed_selected_metadata",
                                        return_value={
                                            "path": "downloads/Coldplay - Yellow.m4a",
                                            "container": "m4a",
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
        self.assertEqual(result["selected_metadata"], selected_metadata.model_dump())
        self.assertEqual(result["selected_download"], selected_download.model_dump())
        self.assertEqual(result["download_result"], download_result)
        self.assertEqual(
            result["tagging_result"],
            {
                "path": "downloads/Coldplay - Yellow.m4a",
                "container": "m4a",
            },
        )
        mock_fetch.assert_called_once()
        mock_select.assert_called_once()
        mock_download_select.assert_called_once()
        mock_download.assert_called_once_with(
            "https://www.youtube.com/watch?v=abc123",
            audio_format="m4a",
            filename="Coldplay - Yellow",
        )
        mock_tag.assert_called_once_with(
            "downloads/Coldplay - Yellow.m4a",
            selected_metadata,
        )
        self.assertEqual(mock_fetch.call_args.args[0], "Yellow")
        self.assertEqual(mock_fetch.call_args.kwargs["artist"], "Coldplay")
        self.assertEqual(mock_fetch.call_args.kwargs["limit"], 4)

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
            "selected_metadata": None,
            "selected_download": None,
            "download_result": None,
            "tagging_result": None,
        }

        with patch.object(app_main, "run_pipeline", return_value=payload):
            with patch("sys.stdout", stdout):
                exit_code = app_main.main(["download", "Yellow", "by", "Coldplay"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue()), payload)


if __name__ == "__main__":
    unittest.main()
