"""
BasePlugin — the base class every CloudStream Desktop extension must subclass.
Equivalent to CloudStream Android's BasePlugin / Plugin classes.
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Optional, Callable
from dataclasses import dataclass

if TYPE_CHECKING:
    from core.main_api import MainAPI
    from core.extractor_api import ExtractorApi


@dataclass
class PluginManifest:
    name: str
    plugin_class_name: str
    version: int
    internal_name: str = ""
    description: str = ""
    author: str = ""
    requires_resources: bool = False
    icon_url: Optional[str] = None
    language: str = "en"
    tv_types: list = None

    def __post_init__(self):
        if self.tv_types is None:
            self.tv_types = []


class BasePlugin:
    """
    Base class for all CloudStream Desktop plugins.

    Plugin authors must subclass this, implement load(), and call
    register_main_api() / register_extractor_api() inside load().

    Example::

        from plugins.base_plugin import BasePlugin
        from my_provider import MyProvider

        class MyPlugin(BasePlugin):
            def load(self):
                self.register_main_api(MyProvider())
    """

    filename: str = ""
    manifest: Optional[PluginManifest] = None
    open_settings: Optional[Callable] = None

    def load(self) -> None:
        """Called when the plugin is loaded. Register APIs here."""
        pass

    def before_unload(self) -> None:
        """Called before the plugin is unloaded. Clean up resources here."""
        pass

    def register_main_api(self, api: "MainAPI") -> None:
        """Register a MainAPI provider with the global APIHolder."""
        from core.api_holder import APIHolder
        api.source_plugin = self.filename
        APIHolder.add_plugin_mapping(api)

    def register_extractor_api(self, extractor: "ExtractorApi") -> None:
        """Register an ExtractorApi with the global APIHolder."""
        from core.api_holder import APIHolder
        extractor.source_plugin = self.filename
        APIHolder.add_extractor(extractor)

    def __repr__(self):
        name = self.manifest.name if self.manifest else self.__class__.__name__
        return f"<Plugin: {name}>"
