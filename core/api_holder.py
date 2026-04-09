from __future__ import annotations
from typing import List, Dict, Optional, TYPE_CHECKING
import threading

if TYPE_CHECKING:
    from core.main_api import MainAPI
    from core.extractor_api import ExtractorApi


class _APIHolder:
    """
    Singleton registry for all MainAPI providers and ExtractorApi extractors.
    Equivalent to CloudStream's APIHolder object.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.all_providers: List["MainAPI"] = []
        self.extractor_apis: List["ExtractorApi"] = []
        self._api_map: Dict[str, "MainAPI"] = {}
        self._callbacks: List[callable] = []

    # ------------------------------------------------------------------
    # Provider management
    # ------------------------------------------------------------------

    def add_plugin_mapping(self, api: "MainAPI") -> None:
        with self._lock:
            if api not in self.all_providers:
                self.all_providers.append(api)
                self._api_map[api.name] = api

    def remove_plugin_mapping(self, api: "MainAPI") -> None:
        with self._lock:
            if api in self.all_providers:
                self.all_providers.remove(api)
            self._api_map.pop(api.name, None)

    def remove_plugin_apis(self, plugin_filename: str) -> None:
        """Remove all APIs registered by a specific plugin file."""
        with self._lock:
            to_remove = [p for p in self.all_providers
                         if getattr(p, "source_plugin", None) == plugin_filename]
            for api in to_remove:
                self.all_providers.remove(api)
                self._api_map.pop(api.name, None)

    def get_api_by_name(self, name: str) -> Optional["MainAPI"]:
        return self._api_map.get(name)

    @property
    def apis(self) -> List["MainAPI"]:
        """Deduplicated list of providers."""
        seen = set()
        result = []
        for p in self.all_providers:
            key = p.name
            if key not in seen:
                seen.add(key)
                result.append(p)
        return result

    # ------------------------------------------------------------------
    # Extractor management
    # ------------------------------------------------------------------

    def add_extractor(self, extractor: "ExtractorApi") -> None:
        with self._lock:
            self.extractor_apis.append(extractor)

    def remove_plugin_extractors(self, plugin_filename: str) -> None:
        with self._lock:
            self.extractor_apis = [
                e for e in self.extractor_apis
                if getattr(e, "source_plugin", None) != plugin_filename
            ]

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def on_plugins_loaded(self, callback: callable) -> None:
        """Register a callback to be invoked after all plugins are loaded."""
        self._callbacks.append(callback)

    def notify_plugins_loaded(self) -> None:
        for cb in self._callbacks:
            try:
                cb()
            except Exception as e:
                print(f"[APIHolder] Callback error: {e}")

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def get_providers_for_type(self, tv_type=None) -> List["MainAPI"]:
        if tv_type is None:
            return self.apis
        return [p for p in self.apis if tv_type in getattr(p, "supported_types", [])]

    def clear_all(self) -> None:
        with self._lock:
            self.all_providers.clear()
            self.extractor_apis.clear()
            self._api_map.clear()

    def __repr__(self):
        return (f"<APIHolder providers={len(self.all_providers)} "
                f"extractors={len(self.extractor_apis)}>")


# Global singleton instance
APIHolder = _APIHolder()
