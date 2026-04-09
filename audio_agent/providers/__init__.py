__all__ = ["OllamaConfig", "build_ollama_client", "generate_structured_response"]


def __getattr__(name: str):
    if name == "OllamaConfig":
        from audio_agent.providers.ollama import OllamaConfig

        return OllamaConfig
    if name == "build_ollama_client":
        from audio_agent.providers.ollama import build_ollama_client

        return build_ollama_client
    if name == "generate_structured_response":
        from audio_agent.providers.ollama import generate_structured_response

        return generate_structured_response
    raise AttributeError(f"module 'audio_agent.providers' has no attribute {name!r}")
