from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request

DEFAULT_ITUNES_BASE_URL = "https://itunes.apple.com/search"
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
        with request.urlopen(raw_request, timeout=active_config.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:  # pragma: no cover - depends on live API
        raise RuntimeError(
            f"iTunes Search API request failed with status {exc.code} for {url}."
        ) from exc
    except error.URLError as exc:  # pragma: no cover - depends on network
        raise RuntimeError(f"Failed to reach iTunes Search API at {url}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("iTunes Search API returned invalid JSON.") from exc
