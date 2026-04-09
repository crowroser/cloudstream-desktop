"""
SQLite database layer for watch history, bookmarks, downloads and search history.
"""
from __future__ import annotations
import sqlite3
import time
import json
from pathlib import Path
from typing import List, Optional
import os

from core.models import (
    WatchHistoryEntry, BookmarkEntry, DownloadEntry, TvType
)

DB_PATH = Path(os.path.expanduser("~")) / ".cloudstream-desktop" / "cloudstream.db"


class _Database:
    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self) -> None:
        cur = self._conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS watch_history (
                url TEXT NOT NULL,
                api_name TEXT NOT NULL,
                name TEXT NOT NULL,
                poster_url TEXT,
                episode INTEGER,
                season INTEGER,
                position REAL DEFAULT 0,
                duration REAL DEFAULT 0,
                timestamp INTEGER NOT NULL,
                episode_data TEXT,
                episode_name TEXT,
                PRIMARY KEY (url, api_name, episode, season)
            );

            CREATE TABLE IF NOT EXISTS bookmarks (
                url TEXT NOT NULL,
                api_name TEXT NOT NULL,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                poster_url TEXT,
                timestamp INTEGER NOT NULL,
                PRIMARY KEY (url, api_name)
            );

            CREATE TABLE IF NOT EXISTS downloads (
                id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                episode_name TEXT,
                file_path TEXT NOT NULL,
                total_bytes INTEGER DEFAULT 0,
                downloaded_bytes INTEGER DEFAULT 0,
                status TEXT DEFAULT 'queued',
                timestamp INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS search_history (
                query TEXT PRIMARY KEY,
                timestamp INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_watch_history_timestamp
                ON watch_history(timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_bookmarks_timestamp
                ON bookmarks(timestamp DESC);
        """)
        self._migrate_watch_history(cur)
        self._conn.commit()

    def _migrate_watch_history(self, cur) -> None:
        cols = {row[1] for row in cur.execute("PRAGMA table_info(watch_history)").fetchall()}
        if "episode_data" not in cols:
            cur.execute("ALTER TABLE watch_history ADD COLUMN episode_data TEXT")
        if "episode_name" not in cols:
            cur.execute("ALTER TABLE watch_history ADD COLUMN episode_name TEXT")

    # ------------------------------------------------------------------
    # Watch History
    # ------------------------------------------------------------------

    def upsert_watch_history(self, entry: WatchHistoryEntry) -> None:
        self._conn.execute("""
            INSERT INTO watch_history
                (url, api_name, name, poster_url, episode, season,
                 position, duration, timestamp, episode_data, episode_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url, api_name, episode, season) DO UPDATE SET
                position=excluded.position,
                duration=excluded.duration,
                timestamp=excluded.timestamp,
                episode_data=COALESCE(excluded.episode_data, episode_data),
                episode_name=COALESCE(excluded.episode_name, episode_name),
                poster_url=COALESCE(excluded.poster_url, poster_url)
        """, (
            entry.url, entry.api_name, entry.name, entry.poster_url,
            entry.episode, entry.season, entry.position, entry.duration,
            entry.timestamp or int(time.time()),
            entry.episode_data, entry.episode_name,
        ))
        self._conn.commit()

    def get_watch_history(self, limit: int = 50) -> List[WatchHistoryEntry]:
        rows = self._conn.execute(
            "SELECT * FROM watch_history ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        return [WatchHistoryEntry(**dict(r)) for r in rows]

    def get_watch_progress(
        self, url: str, api_name: str,
        episode: Optional[int] = None, season: Optional[int] = None
    ) -> Optional[WatchHistoryEntry]:
        row = self._conn.execute(
            "SELECT * FROM watch_history WHERE url=? AND api_name=? AND episode IS ? AND season IS ?",
            (url, api_name, episode, season)
        ).fetchone()
        return WatchHistoryEntry(**dict(row)) if row else None

    def delete_watch_history(self, url: str, api_name: str) -> None:
        self._conn.execute(
            "DELETE FROM watch_history WHERE url=? AND api_name=?", (url, api_name)
        )
        self._conn.commit()

    def get_continue_watching(self, limit: int = 20) -> List[WatchHistoryEntry]:
        """Return the most recent in-progress entry per content (url+api_name)."""
        rows = self._conn.execute("""
            SELECT * FROM watch_history
            WHERE position > 10
              AND duration > 0
              AND (position / duration) < 0.93
              AND episode_data IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,)).fetchall()
        seen = set()
        result = []
        for r in rows:
            d = dict(r)
            key = (d["url"], d["api_name"])
            if key in seen:
                continue
            seen.add(key)
            result.append(WatchHistoryEntry(**d))
        return result

    def clear_watch_history(self) -> None:
        self._conn.execute("DELETE FROM watch_history")
        self._conn.commit()

    # ------------------------------------------------------------------
    # Bookmarks
    # ------------------------------------------------------------------

    def add_bookmark(self, entry: BookmarkEntry) -> None:
        self._conn.execute("""
            INSERT OR REPLACE INTO bookmarks
                (url, api_name, name, type, poster_url, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            entry.url, entry.api_name, entry.name,
            entry.type.value if hasattr(entry.type, "value") else str(entry.type),
            entry.poster_url, entry.timestamp or int(time.time())
        ))
        self._conn.commit()

    def remove_bookmark(self, url: str, api_name: str) -> None:
        self._conn.execute(
            "DELETE FROM bookmarks WHERE url=? AND api_name=?", (url, api_name)
        )
        self._conn.commit()

    def is_bookmarked(self, url: str, api_name: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM bookmarks WHERE url=? AND api_name=?", (url, api_name)
        ).fetchone()
        return row is not None

    def get_bookmarks(self, limit: int = 200) -> List[BookmarkEntry]:
        rows = self._conn.execute(
            "SELECT * FROM bookmarks ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["type"] = TvType(d["type"])
            except ValueError:
                d["type"] = TvType.Others
            result.append(BookmarkEntry(**d))
        return result

    # ------------------------------------------------------------------
    # Downloads
    # ------------------------------------------------------------------

    def upsert_download(self, entry: DownloadEntry) -> None:
        self._conn.execute("""
            INSERT OR REPLACE INTO downloads
                (id, url, title, episode_name, file_path, total_bytes,
                 downloaded_bytes, status, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entry.id, entry.url, entry.title, entry.episode_name,
            entry.file_path, entry.total_bytes, entry.downloaded_bytes,
            entry.status, entry.timestamp or int(time.time())
        ))
        self._conn.commit()

    def get_downloads(self) -> List[DownloadEntry]:
        rows = self._conn.execute(
            "SELECT * FROM downloads ORDER BY timestamp DESC"
        ).fetchall()
        return [DownloadEntry(**dict(r)) for r in rows]

    def delete_download(self, download_id: str) -> None:
        self._conn.execute("DELETE FROM downloads WHERE id=?", (download_id,))
        self._conn.commit()

    # ------------------------------------------------------------------
    # Search History
    # ------------------------------------------------------------------

    def add_search(self, query: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO search_history (query, timestamp) VALUES (?, ?)",
            (query.strip(), int(time.time()))
        )
        self._conn.commit()

    def get_search_history(self, limit: int = 20) -> List[str]:
        rows = self._conn.execute(
            "SELECT query FROM search_history ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        return [r["query"] for r in rows]

    def clear_search_history(self) -> None:
        self._conn.execute("DELETE FROM search_history")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


Database = _Database()
