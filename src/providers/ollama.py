from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel, ValidationError

DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "gemma4:31b-cloud"
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
    response_content = getattr(getattr(response, "message", None), "content", None)
    if not isinstance(response_content, str):
        raise RuntimeError(
            "Ollama response did not include a string message content field."
        )

    validation_error: ValidationError | None = None
    for payload in _candidate_json_payloads(response_content):
        try:
            return response_model.model_validate_json(payload)
        except ValidationError as exc:
            validation_error = exc

    if validation_error is None:
        raise RuntimeError(
            f"Ollama returned data that did not match {response_model.__name__}."
        )

    validation_errors = validation_error.errors(include_url=False, include_input=False)
    response_preview = response_content.strip().replace("\n", "\\n")[:600]
    raise RuntimeError(
        f"Ollama returned data that did not match {response_model.__name__}. "
        f"Validation errors: {validation_errors}. "
        f"Raw response preview: {response_preview}"
    ) from validation_error


def _candidate_json_payloads(response_content: str) -> list[str]:
    candidates: list[str] = []
    stripped = response_content.strip()
    if stripped:
        candidates.append(stripped)

    if stripped.startswith("```"):
        unfenced = re.sub(
            r"^```(?:json)?\s*|\s*```$", "", stripped, flags=re.IGNORECASE
        )
        unfenced = unfenced.strip()
        if unfenced:
            candidates.append(unfenced)

    first_brace = stripped.find("{")
    last_brace = stripped.rfind("}")
    if first_brace != -1 and last_brace != -1 and first_brace < last_brace:
        extracted = stripped[first_brace : last_brace + 1].strip()
        if extracted:
            candidates.append(extracted)

    unique_candidates: list[str] = []
    for candidate in candidates:
        if candidate not in unique_candidates:
            unique_candidates.append(candidate)
    return unique_candidates
