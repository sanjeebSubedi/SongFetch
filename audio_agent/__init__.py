__all__ = [
    "search_song_audio",
    "download_song_audio",
    "build_song_request",
    "parse_download_request",
    "SongRequest",
    "OllamaConfig",
]


def __getattr__(name: str):
    if name == "search_song_audio":
        from audio_agent.tools.search import search_song_audio

        return search_song_audio
    if name == "download_song_audio":
        from audio_agent.tools.download import download_song_audio

        return download_song_audio
    if name == "build_song_request":
        from audio_agent.agents.search_query_builder.agent import build_song_request

        return build_song_request
    if name == "parse_download_request":
        from audio_agent.agents.search_query_builder.agent import parse_download_request

        return parse_download_request
    if name == "SongRequest":
        from audio_agent.agents.search_query_builder.schema import SongRequest

        return SongRequest
    if name == "OllamaConfig":
        from audio_agent.providers.ollama import OllamaConfig

        return OllamaConfig
    raise AttributeError(f"module 'audio_agent' has no attribute {name!r}")
