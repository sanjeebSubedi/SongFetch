from dotenv import load_dotenv

load_dotenv()

__all__ = [
    "search_song_audio",
    "download_song_audio",
    "embed_selected_metadata",
    "fetch_music_metadata",
    "fetch_spotify_metadata",
    "fetch_metadata_from_request",
    "fetch_metadata_from_search_results",
    "fetch_lyrics",
    "import_spotify_playlist_tracks",
    "build_song_request",
    "parse_download_request",
    "build_metadata_lookup_request",
    "build_youtube_fallback_metadata",
    "select_metadata_match",
    "select_download_audio_request",
    "SongRequest",
    "MetadataLookupRequest",
    "MetadataSelection",
    "DownloadAudioSelection",
    "YouTubeFallbackMetadata",
    "TagMetadata",
    "LyricsResult",
    "PlaylistTrack",
    "OllamaConfig",
    "ITunesConfig",
    "LRCLibConfig",
    "SpotifyConfig",
]


def __getattr__(name: str):
    if name == "search_song_audio":
        from src.tools.search import search_song_audio

        return search_song_audio
    if name == "download_song_audio":
        from src.tools.download import download_song_audio

        return download_song_audio
    if name == "embed_selected_metadata":
        from src.tools.tagging import embed_selected_metadata

        return embed_selected_metadata
    if name == "fetch_music_metadata":
        from src.tools.metadata import fetch_music_metadata

        return fetch_music_metadata
    if name == "fetch_spotify_metadata":
        from src.tools.metadata import fetch_spotify_metadata

        return fetch_spotify_metadata
    if name == "fetch_metadata_from_request":
        from src.tools.metadata import fetch_metadata_from_request

        return fetch_metadata_from_request
    if name == "fetch_metadata_from_search_results":
        from src.tools.metadata import fetch_metadata_from_search_results

        return fetch_metadata_from_search_results
    if name == "fetch_lyrics":
        from src.tools.lyrics import fetch_lyrics

        return fetch_lyrics
    if name == "import_spotify_playlist_tracks":
        from src.tools.spotify import import_spotify_playlist_tracks

        return import_spotify_playlist_tracks
    if name == "build_song_request":
        from src.agents.search_query_builder.agent import build_song_request

        return build_song_request
    if name == "parse_download_request":
        from src.agents.search_query_builder.agent import parse_download_request

        return parse_download_request
    if name == "build_metadata_lookup_request":
        from src.agents.metadata_request_builder.agent import (
            build_metadata_lookup_request,
        )

        return build_metadata_lookup_request
    if name == "build_youtube_fallback_metadata":
        from src.agents.youtube_fallback_metadata_builder.agent import (
            build_youtube_fallback_metadata,
        )

        return build_youtube_fallback_metadata
    if name == "select_metadata_match":
        from src.agents.metadata_selector.agent import select_metadata_match

        return select_metadata_match
    if name == "select_download_audio_request":
        from src.agents.download_selector.agent import select_download_audio_request

        return select_download_audio_request
    if name == "SongRequest":
        from src.agents.search_query_builder.schema import SongRequest

        return SongRequest
    if name == "MetadataLookupRequest":
        from src.agents.metadata_request_builder.schema import (
            MetadataLookupRequest,
        )

        return MetadataLookupRequest
    if name == "MetadataSelection":
        from src.agents.metadata_selector.schema import MetadataSelection

        return MetadataSelection
    if name == "DownloadAudioSelection":
        from src.agents.download_selector.schema import DownloadAudioSelection

        return DownloadAudioSelection
    if name == "YouTubeFallbackMetadata":
        from src.agents.youtube_fallback_metadata_builder.schema import (
            YouTubeFallbackMetadata,
        )

        return YouTubeFallbackMetadata
    if name == "TagMetadata":
        from src.types import TagMetadata

        return TagMetadata
    if name == "LyricsResult":
        from src.types import LyricsResult

        return LyricsResult
    if name == "PlaylistTrack":
        from src.types import PlaylistTrack

        return PlaylistTrack
    if name == "OllamaConfig":
        from src.providers.ollama import OllamaConfig

        return OllamaConfig
    if name == "ITunesConfig":
        from src.providers.itunes import ITunesConfig

        return ITunesConfig
    if name == "LRCLibConfig":
        from src.providers.lrclib import LRCLibConfig

        return LRCLibConfig
    if name == "SpotifyConfig":
        from src.providers.spotify import SpotifyConfig

        return SpotifyConfig
    raise AttributeError(f"module 'src' has no attribute {name!r}")
