from __future__ import annotations

import os
from pathlib import Path


def load_env_file(*, override: bool = False) -> None:
    env_path = _default_env_path()
    if not env_path.is_file():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue

        key, value = line.split("=", maxsplit=1)
        normalized_key = key.strip()
        if not normalized_key:
            continue

        if not override and normalized_key in os.environ:
            continue

        normalized_value = value.strip()
        if (
            len(normalized_value) >= 2
            and normalized_value[0] == normalized_value[-1]
            and normalized_value[0] in {"'", '"'}
        ):
            normalized_value = normalized_value[1:-1]

        os.environ[normalized_key] = normalized_value


def _default_env_path() -> Path:
    return Path(__file__).resolve().parent.parent / ".env"
