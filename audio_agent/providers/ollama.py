from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel, ValidationError

DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "gemma4:e2b"
DEFAULT_OLLAMA_TEMPERATURE = 0

ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class OllamaConfig:
    model: str = DEFAULT_OLLAMA_MODEL
    host: str = DEFAULT_OLLAMA_HOST
    temperature: float = DEFAULT_OLLAMA_TEMPERATURE


def build_ollama_client(host: str):
    try:
        from ollama import Client
    except ImportError as exc:  # pragma: no cover - depends on runtime dependencies
        raise RuntimeError(
            "ollama is not installed. Install dependencies first with `pip install -e .`."
        ) from exc

    return Client(host=host)


def generate_structured_response(
    *,
    user_input: str,
    response_model: type[ModelT],
    system_prompt: str,
    config: OllamaConfig | None = None,
) -> ModelT:
    prompt = user_input.strip()
    if not prompt:
        raise ValueError("user_input must not be empty")

    active_config = config or OllamaConfig()
    client = build_ollama_client(active_config.host)
    response = client.chat(
        model=active_config.model,
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        format=response_model.model_json_schema(),
        options={"temperature": active_config.temperature},
    )

    try:
        return response_model.model_validate_json(response.message.content)
    except ValidationError as exc:
        raise RuntimeError(
            f"Ollama returned data that did not match {response_model.__name__}."
        ) from exc
