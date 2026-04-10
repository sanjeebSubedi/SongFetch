__all__ = [
    "OllamaConfig",
    "build_ollama_client",
    "generate_structured_response",
    "ITunesConfig",
    "LRCLibConfig",
    "lookup_lyrics",
    "search_songs",
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
    raise AttributeError(f"module 'src.providers' has no attribute {name!r}")
