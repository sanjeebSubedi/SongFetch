from __future__ import annotations

from src.providers.spotify import SpotifyConfig, fetch_public_playlist
from src.types import PlaylistTrack


def import_spotify_playlist_tracks(
    playlist_ref: str,
    *,
    config: SpotifyConfig | None = None,
) -> dict[str, object]:
    playlist = fetch_public_playlist(playlist_ref, config=config)
    tracks = playlist.get("tracks")
    normalized_tracks = tracks if isinstance(tracks, list) else []
    return {
        "playlist_id": playlist.get("playlist_id"),
        "name": playlist.get("name"),
        "spotify_url": playlist.get("spotify_url"),
        "tracks": [
            track
            for track in normalized_tracks
            if isinstance(track, PlaylistTrack)
        ],
    }
