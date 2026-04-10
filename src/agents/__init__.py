__all__ = [
    "build_song_request",
    "parse_download_request",
    "build_metadata_lookup_request",
    "select_metadata_match",
    "select_download_audio_request",
    "SongRequest",
    "MetadataLookupRequest",
    "MetadataSelection",
    "DownloadAudioSelection",
]


def __getattr__(name: str):
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
    raise AttributeError(f"module 'src.agents' has no attribute {name!r}")
