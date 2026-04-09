"""
JSON-based key-value preferences store (equivalent to Android SharedPreferences).
Thread-safe, auto-saves on write.
"""
from __future__ import annotations
import json
import threading
from pathlib import Path
from typing import Any, Optional
import os

PREFS_PATH = Path(os.path.expanduser("~")) / ".cloudstream-desktop" / "preferences.json"

# Default preference values
DEFAULTS = {
    # Appearance
    "theme": "dark",              # dark | light | system
    "accent_color": "blue",       # blue | green | red | orange
    "language": "tr",
    # Player
    "player_volume": 100,
    "player_subtitles_enabled": True,
    "player_subtitle_size": 24,
    "player_subtitle_lang": "en",
    "player_remember_position": True,
    "player_auto_next": True,
    "player_skip_intro": True,
    "player_preferred_quality": 0,
    "player_preferred_subtitle": "",
    # Downloads
    "download_path": str(Path.home() / "Downloads" / "CloudStream"),
    "max_parallel_downloads": 3,
    # Providers
    "provider_languages": ["en"],
    "show_adult_content": False,
    # Sync
    "anilist_token": None,
    "mal_token": None,
    "simkl_token": None,
    # Extensions
    "auto_update_plugins": True,
    # Misc
    "first_run": True,
}


class _Preferences:
    def __init__(self):
        self._lock = threading.Lock()
        self._data: dict = {}
        self._load()

    def _load(self) -> None:
        PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
        if PREFS_PATH.exists():
            try:
                self._data = json.loads(PREFS_PATH.read_text("utf-8"))
            except Exception:
                self._data = {}
        # Fill in any missing defaults
        for k, v in DEFAULTS.items():
            if k not in self._data:
                self._data[k] = v

    def _save(self) -> None:
        try:
            PREFS_PATH.write_text(json.dumps(self._data, indent=2), "utf-8")
        except Exception as e:
            print(f"[Preferences] Save error: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, DEFAULTS.get(key, default))

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value
            self._save()

    def get_str(self, key: str, default: str = "") -> str:
        return str(self.get(key, default) or default)

    def get_int(self, key: str, default: int = 0) -> int:
        try:
            return int(self.get(key, default))
        except (TypeError, ValueError):
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        val = self.get(key, default)
        if isinstance(val, bool):
            return val
        return str(val).lower() in ("true", "1", "yes")

    def get_list(self, key: str, default: list = None) -> list:
        val = self.get(key, default or [])
        if isinstance(val, list):
            return val
        return default or []

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)
            self._save()

    def reset_to_defaults(self) -> None:
        with self._lock:
            self._data = dict(DEFAULTS)
            self._save()

    def all(self) -> dict:
        with self._lock:
            return dict(self._data)


Preferences = _Preferences()
