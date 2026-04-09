"""
AniList sync provider — GraphQL-based anime tracking.
"""
from __future__ import annotations
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

ANILIST_API = "https://graphql.anilist.co"


@dataclass
class AniListEntry:
    media_id: int
    title: str
    status: str  # CURRENT, COMPLETED, PAUSED, DROPPED, PLANNING
    progress: int
    score: float
    media_type: str  # ANIME, MANGA


class _AniListSync:
    """
    AniList GraphQL sync provider.
    Token: Settings → Sync → AniList → Connect
    Obtain from: https://anilist.co/settings/developer
    """

    def __init__(self):
        from data.preferences import Preferences
        self._prefs = Preferences

    @property
    def token(self) -> Optional[str]:
        return self._prefs.get_str("anilist_token") or None

    @property
    def is_authenticated(self) -> bool:
        return bool(self.token)

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    async def _gql(self, query: str, variables: Dict = None) -> Dict:
        from core.utils.http_helper import post_json
        payload = {"query": query, "variables": variables or {}}
        return await post_json(ANILIST_API, json_data=payload, headers=self._headers())

    async def get_user_id(self) -> Optional[int]:
        query = "query { Viewer { id name } }"
        try:
            data = await self._gql(query)
            return data["data"]["Viewer"]["id"]
        except Exception:
            return None

    async def get_watching_list(self) -> List[AniListEntry]:
        user_id = await self.get_user_id()
        if not user_id:
            return []

        query = """
        query($userId: Int) {
          MediaListCollection(userId: $userId, type: ANIME) {
            lists {
              name
              entries {
                media { id title { romaji english } }
                status progress score
              }
            }
          }
        }
        """
        try:
            data = await self._gql(query, {"userId": user_id})
            lists = data["data"]["MediaListCollection"]["lists"]
            entries = []
            for lst in lists:
                for e in lst["entries"]:
                    title = e["media"]["title"]["english"] or e["media"]["title"]["romaji"]
                    entries.append(AniListEntry(
                        media_id=e["media"]["id"],
                        title=title,
                        status=e["status"],
                        progress=e["progress"],
                        score=e["score"],
                        media_type="ANIME",
                    ))
            return entries
        except Exception as ex:
            print(f"[AniList] get_watching_list error: {ex}")
            return []

    async def update_progress(self, media_id: int, progress: int, status: str = "CURRENT") -> bool:
        if not self.token:
            return False
        mutation = """
        mutation($mediaId: Int, $status: MediaListStatus, $progress: Int) {
          SaveMediaListEntry(mediaId: $mediaId, status: $status, progress: $progress) {
            id status progress
          }
        }
        """
        try:
            await self._gql(mutation, {"mediaId": media_id, "status": status, "progress": progress})
            return True
        except Exception as ex:
            print(f"[AniList] update_progress error: {ex}")
            return False

    async def mark_completed(self, media_id: int, score: float = 0) -> bool:
        if not self.token:
            return False
        mutation = """
        mutation($mediaId: Int, $status: MediaListStatus, $score: Float) {
          SaveMediaListEntry(mediaId: $mediaId, status: $status, score: $score) {
            id
          }
        }
        """
        try:
            await self._gql(mutation, {"mediaId": media_id, "status": "COMPLETED", "score": score})
            return True
        except Exception as ex:
            print(f"[AniList] mark_completed error: {ex}")
            return False

    async def search_anime(self, query: str, limit: int = 10) -> List[Dict]:
        gql = """
        query($search: String, $perPage: Int) {
          Page(perPage: $perPage) {
            media(search: $search, type: ANIME) {
              id title { romaji english } episodes averageScore
              coverImage { medium } status
            }
          }
        }
        """
        try:
            data = await self._gql(gql, {"search": query, "perPage": limit})
            return data["data"]["Page"]["media"]
        except Exception:
            return []


AniListSync = _AniListSync()
