__all__ = [
    "search_song_audio",
    "search_from_request",
    "download_song_audio",
    "embed_selected_metadata",
    "fetch_music_metadata",
    "fetch_metadata_from_request",
    "fetch_metadata_from_search_results",
    "fetch_lyrics",
]


def __getattr__(name: str):
    if name == "search_song_audio":
        from src.tools.search import search_song_audio

        return search_song_audio
    if name == "search_from_request":
        from src.tools.search import search_from_request

        return search_from_request
    if name == "download_song_audio":
        from src.tools.download import download_song_audio

        return download_song_audio
    if name == "embed_selected_metadata":
        from src.tools.tagging import embed_selected_metadata

        return embed_selected_metadata
    if name == "fetch_music_metadata":
        from src.tools.metadata import fetch_music_metadata

        return fetch_music_metadata
    if name == "fetch_metadata_from_request":
        from src.tools.metadata import fetch_metadata_from_request

        return fetch_metadata_from_request
    if name == "fetch_metadata_from_search_results":
        from src.tools.metadata import fetch_metadata_from_search_results

        return fetch_metadata_from_search_results
    if name == "fetch_lyrics":
        from src.tools.lyrics import fetch_lyrics

        return fetch_lyrics
    raise AttributeError(f"module 'src.tools' has no attribute {name!r}")
