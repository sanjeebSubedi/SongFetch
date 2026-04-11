__all__ = [
    "OllamaConfig",
    "build_ollama_client",
    "generate_structured_response",
    "ITunesConfig",
    "LRCLibConfig",
    "SpotifyConfig",
    "lookup_lyrics",
    "search_songs",
    "search_tracks",
    "fetch_public_playlist",
]


def __getattr__(name: str):
    if name == "OllamaConfig":
        from src.providers.ollama import OllamaConfig

        return OllamaConfig
    if name == "build_ollama_client":
        from src.providers.ollama import build_ollama_client

        return build_ollama_client
    if name == "generate_structured_response":
        from src.providers.ollama import generate_structured_response

        return generate_structured_response
    if name == "ITunesConfig":
        from src.providers.itunes import ITunesConfig

        return ITunesConfig
    if name == "search_songs":
        from src.providers.itunes import search_songs

        return search_songs
    if name == "LRCLibConfig":
        from src.providers.lrclib import LRCLibConfig

        return LRCLibConfig
    if name == "lookup_lyrics":
        from src.providers.lrclib import lookup_lyrics

        return lookup_lyrics
    if name == "SpotifyConfig":
        from src.providers.spotify import SpotifyConfig

        return SpotifyConfig
    if name == "search_tracks":
        from src.providers.spotify import search_tracks

        return search_tracks
    if name == "fetch_public_playlist":
        from src.providers.spotify import fetch_public_playlist

        return fetch_public_playlist
    raise AttributeError(f"module 'src.providers' has no attribute {name!r}")
