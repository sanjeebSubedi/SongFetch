__all__ = [
    "OllamaConfig",
    "build_ollama_client",
    "generate_structured_response",
    "MusicBrainzConfig",
    "search_recordings",
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
    if name == "MusicBrainzConfig":
        from src.providers.musicbrainz import MusicBrainzConfig

        return MusicBrainzConfig
    if name == "search_recordings":
        from src.providers.musicbrainz import search_recordings

        return search_recordings
    raise AttributeError(f"module 'src.providers' has no attribute {name!r}")
