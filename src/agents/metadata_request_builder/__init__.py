__all__ = ["build_metadata_lookup_request", "MetadataLookupRequest"]


def __getattr__(name: str):
    if name == "build_metadata_lookup_request":
        from src.agents.metadata_request_builder.agent import (
            build_metadata_lookup_request,
        )

        return build_metadata_lookup_request
    if name == "MetadataLookupRequest":
        from src.agents.metadata_request_builder.schema import (
            MetadataLookupRequest,
        )

        return MetadataLookupRequest
    raise AttributeError(
        "module 'src.agents.metadata_request_builder' "
        f"has no attribute {name!r}"
    )
