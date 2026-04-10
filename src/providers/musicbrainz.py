from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any
from urllib import error, parse, request

DEFAULT_MUSICBRAINZ_BASE_URL = "https://musicbrainz.org/ws/2"
DEFAULT_MUSICBRAINZ_RATE_LIMIT_SECONDS = 1.0
DEFAULT_MUSICBRAINZ_TIMEOUT_SECONDS = 10.0
DEFAULT_MUSICBRAINZ_USER_AGENT = os.environ.get(
    "MUSICBRAINZ_USER_AGENT",
    "audio-agent/0.1.0",
)

_request_lock = Lock()
_last_request_started_at = 0.0


@dataclass(frozen=True, slots=True)
class MusicBrainzConfig:
    base_url: str = DEFAULT_MUSICBRAINZ_BASE_URL
    user_agent: str = DEFAULT_MUSICBRAINZ_USER_AGENT
    rate_limit_seconds: float = DEFAULT_MUSICBRAINZ_RATE_LIMIT_SECONDS
    timeout_seconds: float = DEFAULT_MUSICBRAINZ_TIMEOUT_SECONDS


def search_recordings(
    query: str,
    *,
    limit: int = 5,
    config: MusicBrainzConfig | None = None,
) -> dict[str, Any]:
    search_query = query.strip()
    if not search_query:
        raise ValueError("query must not be empty")

    active_config = config or MusicBrainzConfig()
    normalized_limit = min(max(1, limit), 100)
    _respect_rate_limit(active_config.rate_limit_seconds)

    query_string = parse.urlencode(
        {
            "query": search_query,
            "limit": normalized_limit,
            "fmt": "json",
        }
    )
    url = f"{active_config.base_url.rstrip('/')}/recording?{query_string}"
    raw_request = request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": active_config.user_agent,
        },
        method="GET",
    )

    try:
        with request.urlopen(raw_request, timeout=active_config.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:  # pragma: no cover - depends on live API
        raise RuntimeError(
            f"MusicBrainz request failed with status {exc.code} for {url}."
        ) from exc
    except error.URLError as exc:  # pragma: no cover - depends on network
        raise RuntimeError(f"Failed to reach MusicBrainz at {url}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("MusicBrainz returned invalid JSON.") from exc


def _respect_rate_limit(rate_limit_seconds: float) -> None:
    global _last_request_started_at

    with _request_lock:
        now = time.monotonic()
        remaining = rate_limit_seconds - (now - _last_request_started_at)
        if remaining > 0:
            time.sleep(remaining)
        _last_request_started_at = time.monotonic()
