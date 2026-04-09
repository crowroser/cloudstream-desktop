"""
MyAnimeList sync provider — MAL v2 API (OAuth2).
"""
from __future__ import annotations
from typing import Optional, Dict, List, Any
from dataclasses import dataclass

MAL_API = "https://api.myanimelist.net/v2"
MAL_CLIENT_ID = "6114d00ca681b7701d1e15fe11a4987e"  # Public demo client; users should set their own


@dataclass
class MALEntry:
    mal_id: int
    title: str
    status: str  # watching, completed, on_hold, dropped, plan_to_watch
    num_episodes_watched: int
    score: int
    anime_type: str


class _MALSync:
    """
    MyAnimeList v2 API sync provider.
    Token obtained via OAuth2; store in preferences as mal_token.
    """

    def __init__(self):
        from data.preferences import Preferences
        self._prefs = Preferences

    @property
    def token(self) -> Optional[str]:
        return self._prefs.get_str("mal_token") or None

    @property
    def is_authenticated(self) -> bool:
        return bool(self.token)

    def _headers(self) -> Dict[str, str]:
        h = {"X-MAL-CLIENT-ID": MAL_CLIENT_ID}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    async def get_user_animelist(
        self, status: str = "watching", limit: int = 100
    ) -> List[MALEntry]:
        from core.utils.http_helper import get_json
        url = (
            f"{MAL_API}/users/@me/animelist"
            f"?status={status}&limit={limit}"
            "&fields=list_status,num_episodes,media_type"
        )
        try:
            data = await get_json(url, headers=self._headers())
            entries = []
            for item in data.get("data", []):
                node = item["node"]
                ls = item.get("list_status", {})
                entries.append(MALEntry(
                    mal_id=node["id"],
                    title=node["title"],
                    status=ls.get("status", ""),
                    num_episodes_watched=ls.get("num_episodes_watched", 0),
                    score=ls.get("score", 0),
                    anime_type=node.get("media_type", ""),
                ))
            return entries
        except Exception as ex:
            print(f"[MAL] get_user_animelist error: {ex}")
            return []

    async def update_progress(self, anime_id: int, episodes_watched: int, status: str = "watching") -> bool:
        if not self.token:
            return False
        from core.utils.http_helper import post
        url = f"{MAL_API}/anime/{anime_id}/my_list_status"
        try:
            resp = await post(
                url,
                data={"status": status, "num_watched_episodes": str(episodes_watched)},
                headers=self._headers(),
            )
            return resp.status_code == 200
        except Exception as ex:
            print(f"[MAL] update_progress error: {ex}")
            return False

    async def search_anime(self, query: str, limit: int = 10) -> List[Dict]:
        from core.utils.http_helper import get_json
        url = f"{MAL_API}/anime?q={query}&limit={limit}&fields=id,title,main_picture,num_episodes,mean"
        try:
            data = await get_json(url, headers=self._headers())
            return data.get("data", [])
        except Exception:
            return []

    async def get_anime_details(self, anime_id: int) -> Optional[Dict]:
        from core.utils.http_helper import get_json
        url = (
            f"{MAL_API}/anime/{anime_id}"
            "?fields=id,title,synopsis,mean,status,num_episodes,genres,main_picture"
        )
        try:
            return await get_json(url, headers=self._headers())
        except Exception:
            return None

    def get_oauth_url(self, code_verifier: str) -> str:
        """Generate OAuth2 authorization URL for MAL."""
        import hashlib, base64
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).rstrip(b"=").decode()
        return (
            f"https://myanimelist.net/v1/oauth2/authorize"
            f"?response_type=code&client_id={MAL_CLIENT_ID}"
            f"&code_challenge={code_challenge}&code_challenge_method=plain"
        )

    async def exchange_code(self, code: str, code_verifier: str) -> Optional[str]:
        """Exchange an OAuth2 code for an access token."""
        from core.utils.http_helper import post
        try:
            resp = await post(
                "https://myanimelist.net/v1/oauth2/token",
                data={
                    "client_id": MAL_CLIENT_ID,
                    "grant_type": "authorization_code",
                    "code": code,
                    "code_verifier": code_verifier,
                },
            )
            token = resp.json().get("access_token")
            if token:
                from data.preferences import Preferences
                Preferences.set("mal_token", token)
            return token
        except Exception as ex:
            print(f"[MAL] exchange_code error: {ex}")
            return None


MALSync = _MALSync()
