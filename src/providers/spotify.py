from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from spotify_scraper import SpotifyClient

from src.types import MusicMetadataResult, PlaylistTrack

DEFAULT_SPOTIFY_BROWSER_TYPE = os.environ.get("SPOTIFY_BROWSER_TYPE", "selenium")
DEFAULT_SPOTIFY_BROWSER_NAME = os.environ.get("SPOTIFY_BROWSER_NAME", "chrome")
DEFAULT_SPOTIFY_HEADLESS = os.environ.get("SPOTIFY_HEADLESS", "true").lower() != "false"
DEFAULT_SPOTIFY_USE_WEBDRIVER_MANAGER = (
    os.environ.get("SPOTIFY_USE_WEBDRIVER_MANAGER", "true").lower() != "false"
)
DEFAULT_SPOTIFY_TIMEOUT_SECONDS = float(
    os.environ.get("SPOTIFY_TIMEOUT_SECONDS", "10")
)
DEFAULT_SPOTIFY_SCROLL_PAUSE_SECONDS = float(
    os.environ.get("SPOTIFY_SCROLL_PAUSE_SECONDS", "1.2")
)
DEFAULT_SPOTIFY_MAX_IDLE_SCROLLS = int(
    os.environ.get("SPOTIFY_MAX_IDLE_SCROLLS", "12")
)
_SPOTIFY_BASE_URL = "https://open.spotify.com"
_MAX_SEARCH_MULTIPLIER = 3

_TRACK_URLS_SCRIPT = """
const urls = [];
const seen = new Set();

const rowLinks = Array.from(
  document.querySelectorAll('[data-testid="tracklist-row"] a[data-testid="internal-track-link"][href*="/track/"]')
);
const fallbackLinks = Array.from(document.querySelectorAll('a[href*="/track/"]'));

for (const link of [...rowLinks, ...fallbackLinks]) {
  const href = link.getAttribute('href');
  if (!href) {
    continue;
  }
  const absoluteUrl = href.startsWith('http') ? href : `https://open.spotify.com${href}`;
  if (seen.has(absoluteUrl)) {
    continue;
  }
  seen.add(absoluteUrl);
  urls.push(absoluteUrl);
}

return urls;
"""

_LOCATE_PLAYLIST_SCROLLER_SCRIPT = """
const candidates = Array.from(document.querySelectorAll('div')).filter((el) => {
  const style = getComputedStyle(el);
  return (
    (style.overflowY === 'auto' || style.overflowY === 'scroll') &&
    el.scrollHeight > el.clientHeight + 20
  );
});

const scroller = candidates.find((el) => {
  const text = el.innerText || '';
  return text.includes('songs') && text.includes('Title') && text.includes('Album');
}) || candidates[0] || null;

window.__playlistScroller = scroller;
return !!scroller;
"""

_ADVANCE_PLAYLIST_SCROLLER_SCRIPT = """
const scroller = window.__playlistScroller;
if (!scroller) {
  return null;
}

const previousTop = scroller.scrollTop;
const nextTop = Math.min(
  previousTop + Math.max(scroller.clientHeight * 0.9, 400),
  Math.max(scroller.scrollHeight - scroller.clientHeight, 0)
);
scroller.scrollTop = nextTop;

return {
  previousTop,
  currentTop: scroller.scrollTop,
};
"""

_PLAYLIST_ROWS_SCRIPT = """
const rows = Array.from(document.querySelectorAll('[data-testid="tracklist-row"]'));
return rows.map((row) => {
  const positionText =
    row.querySelector('[aria-colindex="1"] span[data-encore-id="text"]')?.textContent ||
    row.querySelector('[aria-colindex="1"]')?.textContent ||
    '';
  const positionMatch = positionText.match(/\\d+/);

  const titleEl =
    row.querySelector('a[data-testid="internal-track-link"][href*="/track/"]') ||
    row.querySelector('a[href*="/track/"]');

  const artistEls = Array.from(row.querySelectorAll('[aria-colindex="2"] a[href*="/artist/"]'));
  const albumEl =
    row.querySelector('[aria-colindex="3"] a[href*="/album/"]') ||
    row.querySelector('a[href*="/album/"]');

  return {
    position: positionMatch ? parseInt(positionMatch[0], 10) : null,
    title: titleEl ? titleEl.textContent.trim() : null,
    track_url: titleEl ? titleEl.getAttribute('href') : null,
    artists: artistEls.map((el) => el.textContent.trim()).filter(Boolean),
    album: albumEl ? albumEl.textContent.trim() : null,
    album_url: albumEl ? albumEl.getAttribute('href') : null,
  };
}).filter((row) => row.title);
"""


@dataclass(frozen=True, slots=True)
class SpotifyConfig:
    browser_type: str = DEFAULT_SPOTIFY_BROWSER_TYPE
    browser_name: str = DEFAULT_SPOTIFY_BROWSER_NAME
    headless: bool = DEFAULT_SPOTIFY_HEADLESS
    use_webdriver_manager: bool = DEFAULT_SPOTIFY_USE_WEBDRIVER_MANAGER
    timeout_seconds: float = DEFAULT_SPOTIFY_TIMEOUT_SECONDS
    scroll_pause_seconds: float = DEFAULT_SPOTIFY_SCROLL_PAUSE_SECONDS
    max_idle_scrolls: int = DEFAULT_SPOTIFY_MAX_IDLE_SCROLLS


def search_tracks(
    query: str,
    *,
    artist: str | None = None,
    album: str | None = None,
    limit: int = 5,
    config: SpotifyConfig | None = None,
) -> list[MusicMetadataResult]:
    active_config = config or SpotifyConfig()
    normalized_query = _build_search_query(query, artist=artist, album=album)
    if not normalized_query:
        return []

    if active_config.browser_type.strip().lower() != "selenium":
        return []

    try:
        candidate_urls = _discover_track_urls(
            normalized_query,
            limit=max(limit * _MAX_SEARCH_MULTIPLIER, limit),
            config=active_config,
        )
    except Exception:
        return []

    if not candidate_urls:
        return []

    try:
        client = _build_track_client()
    except Exception:
        return []
    normalized_tracks: list[MusicMetadataResult] = []
    seen_track_ids: set[str] = set()
    try:
        for url in candidate_urls:
            try:
                raw_track = client.get_track_info(url)
            except Exception:
                continue
            normalized_track = _normalize_track(raw_track, track_url=url)
            if normalized_track is None:
                continue
            track_id = normalized_track["provider_track_id"]
            if track_id in seen_track_ids:
                continue
            seen_track_ids.add(track_id)
            normalized_tracks.append(normalized_track)
            if len(normalized_tracks) >= limit:
                break
    finally:
        _close_client(client)

    return normalized_tracks


def fetch_public_playlist(
    playlist_ref: str,
    *,
    config: SpotifyConfig | None = None,
) -> dict[str, Any]:
    active_config = config or SpotifyConfig()
    if active_config.browser_type.strip().lower() != "selenium":
        raise RuntimeError("Spotify playlist scraping currently requires selenium.")

    playlist_id = extract_playlist_id(playlist_ref)
    if playlist_id is None:
        raise ValueError("playlist_ref must be a Spotify playlist URL or playlist ID")

    playlist_url = _playlist_url(playlist_id)
    try:
        playlist_name, playlist_rows = _scrape_playlist_rows(
            playlist_url,
            config=active_config,
        )
    except Exception as exc:
        raise RuntimeError(f"Spotify playlist lookup failed: {exc}") from exc

    return {
        "playlist_id": playlist_id,
        "name": playlist_name,
        "spotify_url": playlist_url,
        "tracks": _normalize_playlist_rows(playlist_rows, playlist_id=playlist_id),
    }


def extract_playlist_id(playlist_ref: str) -> str | None:
    normalized = playlist_ref.strip()
    if not normalized:
        return None

    match = re.search(r"playlist/([A-Za-z0-9-]+)", normalized)
    if match:
        return match.group(1)
    if re.fullmatch(r"[A-Za-z0-9-]+", normalized):
        return normalized
    return None


def _build_search_query(
    title: str,
    *,
    artist: str | None = None,
    album: str | None = None,
) -> str:
    parts = []
    for value in (title, artist, album):
        if not isinstance(value, str):
            continue
        normalized = value.strip()
        if normalized:
            parts.append(normalized)
    return " ".join(parts)


def _discover_track_urls(
    search_query: str,
    *,
    limit: int,
    config: SpotifyConfig,
) -> list[str]:
    driver = _build_webdriver(config)
    try:
        driver.set_page_load_timeout(max(int(config.timeout_seconds), 5))
        driver.get(_search_url(search_query))
        _dismiss_cookie_banner(driver)

        _wait_for_track_rows(driver, timeout_seconds=config.timeout_seconds)
        raw_urls = driver.execute_script(_TRACK_URLS_SCRIPT)
        if not isinstance(raw_urls, list):
            return []

        normalized_urls: list[str] = []
        seen: set[str] = set()
        for value in raw_urls:
            absolute_url = _absolute_spotify_url(value)
            if absolute_url is None or absolute_url in seen:
                continue
            seen.add(absolute_url)
            normalized_urls.append(absolute_url)
            if len(normalized_urls) >= limit:
                break
        return normalized_urls
    finally:
        driver.quit()


def _scrape_playlist_rows(
    playlist_url: str,
    *,
    config: SpotifyConfig,
) -> tuple[str, list[dict[str, object]]]:
    driver = _build_webdriver(config)
    try:
        driver.set_page_load_timeout(max(int(config.timeout_seconds), 5))
        driver.get(playlist_url)
        _dismiss_cookie_banner(driver)

        _wait_for_track_rows(driver, timeout_seconds=config.timeout_seconds)
        if not driver.execute_script(_LOCATE_PLAYLIST_SCROLLER_SCRIPT):
            raise RuntimeError("Could not find the Spotify playlist scroll container.")

        playlist_name = _extract_playlist_name(driver)
        rows_by_position: dict[int, dict[str, object]] = {}
        idle_scrolls = 0

        while idle_scrolls < config.max_idle_scrolls:
            visible_rows = driver.execute_script(_PLAYLIST_ROWS_SCRIPT)
            added_this_round = 0

            if isinstance(visible_rows, list):
                for row in visible_rows:
                    if not isinstance(row, dict):
                        continue
                    position = _optional_int(row.get("position"))
                    if position is None or position in rows_by_position:
                        continue
                    rows_by_position[position] = row
                    added_this_round += 1

            moved = _advance_playlist(driver)
            time.sleep(config.scroll_pause_seconds)

            if added_this_round == 0:
                idle_scrolls += 1
            else:
                idle_scrolls = 0

            if not moved:
                idle_scrolls += 1

        ordered_rows = [rows_by_position[key] for key in sorted(rows_by_position)]
        return playlist_name, ordered_rows
    finally:
        driver.quit()


def _normalize_track(
    raw_track: dict[str, Any],
    *,
    track_url: str,
) -> MusicMetadataResult | None:
    if not isinstance(raw_track, dict):
        return None

    track_id = _first_non_empty(
        _optional_text(raw_track.get("id")),
        _extract_spotify_id(track_url, entity_type="track"),
    )
    if track_id is None:
        return None

    album = raw_track.get("album")
    album_dict = album if isinstance(album, dict) else {}
    album_id = _first_non_empty(
        _optional_text(album_dict.get("id")),
        _extract_spotify_id(_optional_text(album_dict.get("uri")), entity_type="album"),
        _extract_spotify_id(
            _external_spotify_url(album_dict.get("external_urls")),
            entity_type="album",
        ),
    )
    album_url = (
        _external_spotify_url(album_dict.get("external_urls"))
        or (_album_url(album_id) if album_id else None)
    )
    normalized_track_url = (
        _external_spotify_url(raw_track.get("external_urls"))
        or _absolute_spotify_url(track_url)
        or _track_url(track_id)
    )
    explicit = raw_track.get("explicit")

    return {
        "provider": "spotify",
        "provider_track_id": track_id,
        "provider_collection_id": album_id,
        "title": _optional_text(raw_track.get("name")),
        "artist": _primary_artist_name(raw_track.get("artists")),
        "album": _optional_text(album_dict.get("name")),
        "release_date": _optional_text(album_dict.get("release_date")),
        "duration_ms": _optional_int(raw_track.get("duration_ms")),
        "explicitness": (
            "explicit"
            if explicit is True
            else "notExplicit" if explicit is False else None
        ),
        "is_explicit": explicit if isinstance(explicit, bool) else None,
        "track_number": _optional_int(raw_track.get("track_number")),
        "disc_number": _optional_int(raw_track.get("disc_number")),
        "genre": None,
        "artwork_url": _largest_image_url(album_dict.get("images")),
        "preview_url": _optional_text(raw_track.get("preview_url")),
        "track_view_url": normalized_track_url,
        "collection_view_url": album_url,
    }


def _normalize_playlist_row(
    row: dict[str, object],
    *,
    playlist_id: str,
) -> PlaylistTrack | None:
    title = _optional_text(row.get("title"))
    artists_value = row.get("artists")
    if not title or not isinstance(artists_value, list):
        return None

    artists = [
        artist.strip()
        for artist in artists_value
        if isinstance(artist, str) and artist.strip()
    ]
    if not artists:
        return None

    track_url = _absolute_spotify_url(row.get("track_url"))
    track_id = _first_non_empty(
        _extract_spotify_id(track_url, entity_type="track"),
        _fallback_playlist_track_id(
            playlist_id=playlist_id,
            position=_optional_int(row.get("position")),
            title=title,
            artist=artists[0],
        ),
    )
    if track_id is None:
        return None

    return PlaylistTrack(
        provider="spotify",
        provider_track_id=track_id,
        title=title,
        artist=", ".join(artists),
        album=_optional_text(row.get("album")),
        artwork_url=None,
        spotify_track_url=track_url,
    )


def _normalize_playlist_rows(
    rows: list[dict[str, object]],
    *,
    playlist_id: str,
) -> list[PlaylistTrack]:
    normalized_tracks: list[PlaylistTrack] = []
    for row in rows:
        normalized_track = _normalize_playlist_row(row, playlist_id=playlist_id)
        if normalized_track is not None:
            normalized_tracks.append(normalized_track)
    return normalized_tracks


def _build_track_client() -> SpotifyClient:
    return SpotifyClient()


def _close_client(client: SpotifyClient) -> None:
    try:
        client.close()
    except Exception:
        pass


def _build_webdriver(config: SpotifyConfig):
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.firefox.service import Service as FirefoxService

    browser_name = config.browser_name.strip().lower()
    if browser_name == "firefox":
        options = webdriver.FirefoxOptions()
        if config.headless:
            options.add_argument("--headless")
        options.add_argument("--width=1920")
        options.add_argument("--height=1080")

        if config.use_webdriver_manager:
            from webdriver_manager.firefox import GeckoDriverManager

            service = FirefoxService(GeckoDriverManager().install())
            return webdriver.Firefox(service=service, options=options)
        return webdriver.Firefox(options=options)

    if browser_name != "chrome":
        raise RuntimeError(
            f"Unsupported Spotify browser: {config.browser_name}. Use chrome or firefox."
        )

    options = webdriver.ChromeOptions()
    if config.headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    if config.use_webdriver_manager:
        from webdriver_manager.chrome import ChromeDriverManager

        service = ChromeService(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)
    return webdriver.Chrome(options=options)


def _dismiss_cookie_banner(driver) -> None:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    selectors = (
        "button[data-testid='cookie-banner-accept-button']",
        "button#onetrust-accept-btn-handler",
    )
    for selector in selectors:
        try:
            button = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
            )
        except Exception:
            continue
        button.click()
        time.sleep(0.5)
        break


def _wait_for_track_rows(driver, *, timeout_seconds: float) -> None:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    wait_seconds = max(int(timeout_seconds), 5)
    WebDriverWait(driver, wait_seconds).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="tracklist-row"]'))
    )


def _extract_playlist_name(driver) -> str:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    selectors = ("main h1", '[data-testid="entityTitle"]', "h1")
    for selector in selectors:
        try:
            element = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
        except Exception:
            continue
        text = element.text.strip()
        if text:
            return text
    return "Unknown Playlist"


def _advance_playlist(driver) -> bool:
    scroll_state = driver.execute_script(_ADVANCE_PLAYLIST_SCROLLER_SCRIPT)
    if not isinstance(scroll_state, dict):
        return False
    previous_top = scroll_state.get("previousTop")
    current_top = scroll_state.get("currentTop")
    return (
        isinstance(previous_top, (int, float))
        and isinstance(current_top, (int, float))
        and current_top > previous_top
    )


def _search_url(query: str) -> str:
    return f"{_SPOTIFY_BASE_URL}/search/{quote(query)}/tracks"


def _playlist_url(playlist_id: str) -> str:
    return f"{_SPOTIFY_BASE_URL}/playlist/{playlist_id}"


def _track_url(track_id: str) -> str:
    return f"{_SPOTIFY_BASE_URL}/track/{track_id}"


def _album_url(album_id: str) -> str:
    return f"{_SPOTIFY_BASE_URL}/album/{album_id}"


def _absolute_spotify_url(value: object) -> str | None:
    text = _optional_text(value)
    if text is None:
        return None
    if text.startswith("http://") or text.startswith("https://"):
        return text
    if text.startswith("/"):
        return f"{_SPOTIFY_BASE_URL}{text}"
    return None


def _extract_spotify_id(value: str | None, *, entity_type: str) -> str | None:
    if not value:
        return None
    path_pattern = rf"/{entity_type}/([A-Za-z0-9-]+)"
    uri_pattern = rf"spotify:{entity_type}:([A-Za-z0-9-]+)"
    for pattern in (path_pattern, uri_pattern):
        match = re.search(pattern, value)
        if match:
            return match.group(1)
    return None


def _external_spotify_url(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    return _absolute_spotify_url(value.get("spotify"))


def _primary_artist_name(value: object) -> str | None:
    if not isinstance(value, list) or not value:
        return None
    first = value[0]
    if not isinstance(first, dict):
        return None
    return _optional_text(first.get("name"))


def _largest_image_url(value: object) -> str | None:
    if not isinstance(value, list):
        return None
    images = [item for item in value if isinstance(item, dict)]
    if not images:
        return None
    sorted_images = sorted(
        images,
        key=lambda item: item.get("height")
        if isinstance(item.get("height"), int)
        else 0,
        reverse=True,
    )
    return _optional_text(sorted_images[0].get("url"))


def _fallback_playlist_track_id(
    *,
    playlist_id: str,
    position: int | None,
    title: str,
    artist: str,
) -> str | None:
    if position is not None and position > 0:
        return f"{playlist_id}-{position}"
    normalized = re.sub(r"[^a-z0-9]+", "-", f"{artist}-{title}".lower()).strip("-")
    return normalized or None


def _first_non_empty(*values: str | None) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        normalized = value.strip()
        if normalized.isdigit():
            return int(normalized)
    return None
