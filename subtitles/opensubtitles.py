"""
OpenSubtitles REST API v1 subtitle provider.
API docs: https://opensubtitles.stoplight.io/docs/opensubtitles-api
"""
from __future__ import annotations
from typing import List, Optional, Dict
from dataclasses import dataclass

OS_API = "https://api.opensubtitles.com/api/v1"
OS_APP_NAME = "CloudStreamDesktop v1.0"

# Default public API key (rate-limited). Users can set their own in preferences.
DEFAULT_API_KEY = "uyBLgFD18bQAuFQeXH7oMBXfCKKMRMmi"


@dataclass
class SubtitleResult:
    file_id: int
    language: str
    release: str
    download_count: int
    url: Optional[str] = None
    fps: Optional[float] = None
    format: str = "srt"


class _OpenSubtitlesProvider:
    """
    Search and download subtitles from OpenSubtitles.com.
    """

    def __init__(self):
        from data.preferences import Preferences
        self._prefs = Preferences
        self._token: Optional[str] = None

    @property
    def api_key(self) -> str:
        return self._prefs.get_str("opensubtitles_api_key") or DEFAULT_API_KEY

    def _headers(self, with_auth: bool = False) -> Dict[str, str]:
        h = {
            "Api-Key": self.api_key,
            "Content-Type": "application/json",
            "User-Agent": OS_APP_NAME,
        }
        if with_auth and self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    async def login(self, username: str, password: str) -> bool:
        from core.utils.http_helper import post_json
        try:
            data = await post_json(
                f"{OS_API}/login",
                json_data={"username": username, "password": password},
                headers=self._headers(),
            )
            self._token = data.get("token")
            return bool(self._token)
        except Exception as ex:
            print(f"[OpenSubtitles] login error: {ex}")
            return False

    async def search(
        self,
        query: str = "",
        imdb_id: str = "",
        tmdb_id: str = "",
        season: Optional[int] = None,
        episode: Optional[int] = None,
        language: str = "en",
    ) -> List[SubtitleResult]:
        from core.utils.http_helper import get_json

        params = {
            "languages": language,
            "order_by": "download_count",
        }
        if query:
            params["query"] = query
        if imdb_id:
            params["imdb_id"] = imdb_id.lstrip("tt")
        if tmdb_id:
            params["tmdb_id"] = tmdb_id
        if season is not None:
            params["season_number"] = season
        if episode is not None:
            params["episode_number"] = episode

        try:
            data = await get_json(f"{OS_API}/subtitles", params=params, headers=self._headers())
            results = []
            for item in data.get("data", []):
                attrs = item.get("attributes", {})
                files = attrs.get("files", [])
                file_id = files[0].get("file_id") if files else None
                if file_id:
                    results.append(SubtitleResult(
                        file_id=file_id,
                        language=attrs.get("language", ""),
                        release=attrs.get("release", ""),
                        download_count=attrs.get("download_count", 0),
                        fps=attrs.get("fps"),
                        format=attrs.get("format", "srt"),
                    ))
            return results
        except Exception as ex:
            print(f"[OpenSubtitles] search error: {ex}")
            return []

    async def get_download_url(self, file_id: int) -> Optional[str]:
        from core.utils.http_helper import post_json
        try:
            data = await post_json(
                f"{OS_API}/download",
                json_data={"file_id": file_id},
                headers=self._headers(with_auth=True),
            )
            return data.get("link")
        except Exception as ex:
            print(f"[OpenSubtitles] get_download_url error: {ex}")
            return None

    async def download_subtitle(self, file_id: int) -> Optional[str]:
        """Download subtitle content as string."""
        from core.utils.http_helper import get_text
        url = await self.get_download_url(file_id)
        if not url:
            return None
        try:
            return await get_text(url)
        except Exception as ex:
            print(f"[OpenSubtitles] download error: {ex}")
            return None

    async def search_and_get_url(
        self,
        title: str,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        language: str = "en",
    ) -> Optional[str]:
        """Convenience: search + get download URL of best result."""
        results = await self.search(
            query=title, season=season, episode=episode, language=language
        )
        if not results:
            return None
        best = max(results, key=lambda r: r.download_count)
        return await self.get_download_url(best.file_id)


OpenSubtitlesProvider = _OpenSubtitlesProvider()
