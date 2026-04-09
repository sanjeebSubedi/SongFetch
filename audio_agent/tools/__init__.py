__all__ = ["search_song_audio", "search_from_request", "download_song_audio"]


def __getattr__(name: str):
    if name == "search_song_audio":
        from audio_agent.tools.search import search_song_audio

        return search_song_audio
    if name == "search_from_request":
        from audio_agent.tools.search import search_from_request

        return search_from_request
    if name == "download_song_audio":
        from audio_agent.tools.download import download_song_audio

        return download_song_audio
    raise AttributeError(f"module 'audio_agent.tools' has no attribute {name!r}")
