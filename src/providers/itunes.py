from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request

_RETRY_DELAYS: tuple[float, ...] = (0.3, 0.7)

DEFAULT_ITUNES_BASE_URL = os.environ.get(
    "ITUNES_BASE_URL", "https://itunes.apple.com/search"
)
DEFAULT_ITUNES_COUNTRY = os.environ.get("ITUNES_COUNTRY", "US")
DEFAULT_ITUNES_MEDIA = "music"
DEFAULT_ITUNES_ENTITY = "song"
DEFAULT_ITUNES_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True, slots=True)
class ITunesConfig:
    base_url: str = DEFAULT_ITUNES_BASE_URL
    country: str = DEFAULT_ITUNES_COUNTRY
    media: str = DEFAULT_ITUNES_MEDIA
    entity: str = DEFAULT_ITUNES_ENTITY
    timeout_seconds: float = DEFAULT_ITUNES_TIMEOUT_SECONDS


def search_songs(
    term: str,
    *,
    limit: int = 5,
    config: ITunesConfig | None = None,
) -> dict[str, Any]:
    search_term = term.strip()
    if not search_term:
        raise ValueError("term must not be empty")

    active_config = config or ITunesConfig()
    normalized_limit = min(max(1, limit), 200)
    query_string = parse.urlencode(
        {
            "term": search_term,
            "media": active_config.media,
            "entity": active_config.entity,
            "country": active_config.country,
            "limit": normalized_limit,
        }
    )
    url = f"{active_config.base_url}?{query_string}"
    raw_request = request.Request(
        url,
        headers={"Accept": "application/json"},
        method="GET",
    )

    try:
        with _urlopen_with_retry(
            raw_request, timeout=active_config.timeout_seconds
        ) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:  # pragma: no cover - depends on live API
        raise RuntimeError(
            f"iTunes Search API request failed with status {exc.code} for {url}."
        ) from exc
    except error.URLError as exc:  # pragma: no cover - depends on network
        raise RuntimeError(
            f"Failed to reach iTunes Search API at {url}: {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("iTunes Search API returned invalid JSON.") from exc


def _urlopen_with_retry(req: request.Request, *, timeout: float):
    last_exc: Exception | None = None
    for attempt in range(len(_RETRY_DELAYS) + 1):
        try:
            return request.urlopen(req, timeout=timeout)
        except error.HTTPError as exc:
            if exc.code in {429, 500, 502, 503, 504} and attempt < len(_RETRY_DELAYS):
                time.sleep(_RETRY_DELAYS[attempt])
                last_exc = exc
                continue
            raise
        except error.URLError as exc:
            if attempt < len(_RETRY_DELAYS):
                time.sleep(_RETRY_DELAYS[attempt])
                last_exc = exc
                continue
            raise
    raise last_exc  # type: ignore[misc]
