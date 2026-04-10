__all__ = ["select_metadata_match", "MetadataSelection"]


def __getattr__(name: str):
    if name == "select_metadata_match":
        from src.agents.metadata_selector.agent import select_metadata_match

        return select_metadata_match
    if name == "MetadataSelection":
        from src.agents.metadata_selector.schema import MetadataSelection

        return MetadataSelection
    raise AttributeError(
        f"module 'src.agents.metadata_selector' has no attribute {name!r}"
    )
