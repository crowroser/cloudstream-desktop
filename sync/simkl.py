"""
Simkl sync provider — movie/TV/anime tracking.
"""
from __future__ import annotations
from typing import Optional, Dict, List

SIMKL_API = "https://api.simkl.com"
SIMKL_CLIENT_ID = ""  # Set in preferences or env


class _SimklSync:
    """
    Simkl API sync provider.
    Requires client_id (simkl.com/settings/developer) and access token.
    """

    def __init__(self):
        from data.preferences import Preferences
        self._prefs = Preferences

    @property
    def token(self) -> Optional[str]:
        return self._prefs.get_str("simkl_token") or None

    @property
    def is_authenticated(self) -> bool:
        return bool(self.token)

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json", "simkl-api-key": SIMKL_CLIENT_ID}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    async def get_user_history(self, media_type: str = "anime") -> List[Dict]:
        from core.utils.http_helper import get_json
        url = f"{SIMKL_API}/sync/all-items/{media_type}"
        try:
            return await get_json(url, headers=self._headers()) or []
        except Exception as ex:
            print(f"[Simkl] get_user_history error: {ex}")
            return []

    async def mark_as_watched(self, simkl_id: int, media_type: str = "movie") -> bool:
        if not self.token:
            return False
        from core.utils.http_helper import post_json
        payload = {
            media_type + "s": [{"ids": {"simkl": simkl_id}}]
        }
        try:
            await post_json(
                f"{SIMKL_API}/sync/history",
                json_data=payload,
                headers=self._headers(),
            )
            return True
        except Exception as ex:
            print(f"[Simkl] mark_as_watched error: {ex}")
            return False

    async def add_to_watchlist(self, simkl_id: int, media_type: str = "movie") -> bool:
        if not self.token:
            return False
        from core.utils.http_helper import post_json
        payload = {
            media_type + "s": [{"ids": {"simkl": simkl_id}}]
        }
        try:
            await post_json(
                f"{SIMKL_API}/sync/watchlist",
                json_data=payload,
                headers=self._headers(),
            )
            return True
        except Exception as ex:
            print(f"[Simkl] add_to_watchlist error: {ex}")
            return False

    async def search(self, query: str, media_type: str = "all", limit: int = 20) -> List[Dict]:
        from core.utils.http_helper import get_json
        url = f"{SIMKL_API}/search/{media_type}?q={query}&limit={limit}"
        try:
            return await get_json(url, headers=self._headers()) or []
        except Exception:
            return []

    def get_oauth_url(self) -> str:
        return (
            f"https://simkl.com/oauth/authorize"
            f"?response_type=code&client_id={SIMKL_CLIENT_ID}"
            "&redirect_uri=urn:ietf:wg:oauth:2.0:oob"
        )

    async def exchange_pin(self, pin: str) -> Optional[str]:
        from core.utils.http_helper import post_json
        try:
            data = await post_json(
                f"{SIMKL_API}/oauth/pin/{pin}",
                json_data={"client_id": SIMKL_CLIENT_ID},
            )
            token = data.get("access_token")
            if token:
                from data.preferences import Preferences
                Preferences.set("simkl_token", token)
            return token
        except Exception as ex:
            print(f"[Simkl] exchange_pin error: {ex}")
            return None


SimklSync = _SimklSync()
