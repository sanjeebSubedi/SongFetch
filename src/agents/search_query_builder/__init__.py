__all__ = ["build_song_request", "parse_download_request", "SongRequest"]


def __getattr__(name: str):
    if name == "build_song_request":
        from src.agents.search_query_builder.agent import build_song_request

        return build_song_request
    if name == "parse_download_request":
        from src.agents.search_query_builder.agent import parse_download_request

        return parse_download_request
    if name == "SongRequest":
        from src.agents.search_query_builder.schema import SongRequest

        return SongRequest
    raise AttributeError(
        f"module 'src.agents.search_query_builder' has no attribute {name!r}"
    )
