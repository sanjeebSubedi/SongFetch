__all__ = ["select_download_audio_request", "DownloadAudioSelection"]


def __getattr__(name: str):
    if name == "select_download_audio_request":
        from src.agents.download_selector.agent import select_download_audio_request

        return select_download_audio_request
    if name == "DownloadAudioSelection":
        from src.agents.download_selector.schema import DownloadAudioSelection

        return DownloadAudioSelection
    raise AttributeError(
        f"module 'src.agents.download_selector' has no attribute {name!r}"
    )
