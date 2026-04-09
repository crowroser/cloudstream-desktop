"""
CloudStreamApp — the main application window.
Sidebar navigation + content area. Equivalent to CloudStream's MainActivity.
"""
from __future__ import annotations
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict, Any, Callable

import customtkinter as ctk
from PIL import Image
import os
from pathlib import Path

from data.preferences import Preferences
from core.i18n import tr

# Navigation pages (lazy imported to avoid circular deps)
NAV_PAGES = ["Home", "Search", "Library", "Downloads", "Settings"]

SIDEBAR_WIDTH = 210

NAV_ICONS = {
    "Home": "⌂",
    "Search": "⌕",
    "Library": "☰",
    "Downloads": "↓",
    "Settings": "⚙",
}

ACCENT_COLOR = ("#1a73e8", "#2196f3")
ACCENT_HOVER = ("#1557b0", "#1976d2")
SIDEBAR_BG = ("gray90", "gray12")
HEADER_BG = ("gray88", "gray14")


class CloudStreamApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Theme & language
        theme = Preferences.get_str("theme", "dark")
        ctk.set_appearance_mode(theme)
        ctk.set_default_color_theme("blue")

        from core.i18n import set_language
        set_language(Preferences.get_str("language", "tr"))

        self.title("CloudStream Desktop")
        self.geometry("1280x760")
        self.minsize(900, 600)

        self._current_page: Optional[str] = None
        self._pages: Dict[str, ctk.CTkFrame] = {}
        self._nav_buttons: Dict[str, ctk.CTkButton] = {}
        self._history: list = []

        self._ensure_bg_loop()

        self._build_layout()
        self._load_plugins_async()
        self._navigate("Home")

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar
        self.sidebar = ctk.CTkFrame(
            self,
            width=SIDEBAR_WIDTH,
            corner_radius=0,
            fg_color=SIDEBAR_BG,
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self._build_sidebar()

        # Content area
        self.content = ctk.CTkFrame(self, corner_radius=0, fg_color=("gray96", "gray10"))
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        # Status bar
        self.status_bar = ctk.CTkLabel(
            self,
            text=tr("Ready"),
            font=ctk.CTkFont(size=11),
            fg_color=("gray82", "gray17"),
            text_color=("gray40", "gray60"),
            anchor="w",
            height=24,
        )
        self.status_bar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=0, pady=0)

    def _build_sidebar(self):
        # Logo / App name
        logo_frame = ctk.CTkFrame(
            self.sidebar,
            fg_color=ACCENT_COLOR,
            corner_radius=0,
            height=72,
        )
        logo_frame.pack(fill="x")
        logo_frame.pack_propagate(False)

        ctk.CTkLabel(
            logo_frame,
            text="☁  CloudStream",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color="white",
        ).place(relx=0.5, rely=0.5, anchor="center")

        # Navigation buttons
        nav_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        nav_frame.pack(fill="x", padx=6, pady=(12, 4))

        for page in NAV_PAGES[:-1]:  # Settings hariç hepsi
            btn = self._make_nav_button(nav_frame, page)
            btn.pack(fill="x", pady=2)
            self._nav_buttons[page] = btn

        # Settings at bottom
        ctk.CTkFrame(self.sidebar, fg_color="transparent").pack(expand=True, fill="y")
        ctk.CTkFrame(self.sidebar, height=1, fg_color=("gray75", "gray28")).pack(
            fill="x", padx=10, pady=4
        )
        settings_btn = self._make_nav_button(self.sidebar, "Settings")
        settings_btn.pack(fill="x", padx=6, pady=4)
        self._nav_buttons["Settings"] = settings_btn

        # Plugin count label
        self.plugin_count_label = ctk.CTkLabel(
            self.sidebar,
            text=tr("No plugins loaded"),
            font=ctk.CTkFont(size=10),
            text_color=("gray50", "gray50"),
        )
        self.plugin_count_label.pack(pady=(2, 10))

    def _make_nav_button(self, parent, page: str) -> ctk.CTkButton:
        icon = NAV_ICONS.get(page, "•")
        label = tr(page)
        return ctk.CTkButton(
            parent,
            text=f"  {icon}   {label}",
            anchor="w",
            font=ctk.CTkFont(size=13),
            height=42,
            fg_color="transparent",
            hover_color=("gray78", "gray22"),
            text_color=("gray25", "gray85"),
            corner_radius=8,
            command=lambda p=page: self._navigate(p),
        )

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _navigate(self, page: str, **kwargs):
        if self._current_page == page and not kwargs:
            return

        # Deactivate old button
        if self._current_page and self._current_page in self._nav_buttons:
            self._nav_buttons[self._current_page].configure(
                fg_color="transparent",
                text_color=("gray20", "gray90"),
            )

        # Activate new button
        if page in self._nav_buttons:
            self._nav_buttons[page].configure(
                fg_color=ACCENT_COLOR,
                text_color="white",
            )

        # Stop player if navigating away from it
        if self._current_page == "Player" and page != "Player" and "Player" in self._pages:
            self._pages["Player"]._stop_current()

        # Hide all pages
        for p, frame in self._pages.items():
            frame.grid_remove()

        # Create page if not yet built
        if page not in self._pages:
            self._pages[page] = self._build_page(page)

        # Show the page
        self._pages[page].grid(row=0, column=0, sticky="nsew")
        self._current_page = page

        pg = self._pages[page]
        if hasattr(pg, "navigate"):
            pg.navigate(**kwargs)

    def _build_page(self, page: str) -> ctk.CTkFrame:
        """Lazily build and return a page frame."""
        if page == "Home":
            from ui.home import HomePage
            return HomePage(self.content, app=self)
        elif page == "Search":
            from ui.search import SearchPage
            return SearchPage(self.content, app=self)
        elif page == "Library":
            from ui.library import LibraryPage
            return LibraryPage(self.content, app=self)
        elif page == "Downloads":
            from ui.downloads import DownloadsPage
            return DownloadsPage(self.content, app=self)
        elif page == "Settings":
            from ui.settings.general import SettingsPage
            return SettingsPage(self.content, app=self)
        else:
            frame = ctk.CTkFrame(self.content, fg_color="transparent")
            ctk.CTkLabel(frame, text=f"{page} page", font=ctk.CTkFont(size=20)).pack(
                expand=True
            )
            return frame

    def navigate_to_result(self, result):
        """Navigate to the content detail page with a SearchResponse."""
        self._stop_player_if_active()

        if "Result" not in self._pages:
            from ui.result import ResultPage
            self._pages["Result"] = ResultPage(self.content, app=self)

        for frame in self._pages.values():
            frame.grid_remove()

        page = self._pages["Result"]
        page.grid(row=0, column=0, sticky="nsew")
        page.load_result(result)
        self._history.append(self._current_page)
        self._current_page = "Result"

    def navigate_to_player(self, links, subtitles=None, title="", episode=None,
                           content_url="", api_name="", poster_url="",
                           resume_position: float = 0.0,
                           all_episodes=None):
        """Open the video player as an in-app page."""
        self._stop_player_if_active()

        if "Player" not in self._pages:
            from ui.player import PlayerPage
            self._pages["Player"] = PlayerPage(self.content, app=self)

        for frame in self._pages.values():
            frame.grid_remove()

        page = self._pages["Player"]
        page.grid(row=0, column=0, sticky="nsew")
        page.load(
            links=links, subtitles=subtitles or [], title=title, episode=episode,
            content_url=content_url, api_name=api_name, poster_url=poster_url,
            resume_position=resume_position,
            all_episodes=all_episodes or [],
        )
        self._history.append(self._current_page)
        self._current_page = "Player"

    def _stop_player_if_active(self):
        """Stop video playback if currently on Player page."""
        if self._current_page == "Player" and "Player" in self._pages:
            self._pages["Player"]._stop_current()

    def go_back(self):
        if self._current_page == "Player" and "Player" in self._pages:
            self._pages["Player"]._stop_current()
        if self._history:
            prev = self._history.pop()
            self._navigate(prev)

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def set_status(self, msg: str):
        self.after(0, lambda: self.status_bar.configure(text=f"   {msg}"))

    # ------------------------------------------------------------------
    # Plugin loading
    # ------------------------------------------------------------------

    def _load_plugins_async(self):
        from core.api_holder import APIHolder
        from plugins.plugin_manager import PluginManager

        def _after_loaded():
            count = len(APIHolder.apis)
            self.after(0, lambda: self.plugin_count_label.configure(
                text=f"{count} {tr('providers loaded')}"
            ))
            self.after(0, lambda: self.set_status(
                f"{count} {tr('providers loaded')} ({len(PluginManager.get_loaded_plugins())} eklenti)"
            ))

        APIHolder.on_plugins_loaded(_after_loaded)

        def _load():
            PluginManager.load_all_registered_plugins()

        threading.Thread(target=_load, daemon=True).start()

    # ------------------------------------------------------------------
    # Background event loop (single thread for ALL async work)
    # ------------------------------------------------------------------

    _bg_loop: Optional[asyncio.AbstractEventLoop] = None
    _bg_thread: Optional[threading.Thread] = None
    _image_pool: Optional[ThreadPoolExecutor] = None

    @classmethod
    def _ensure_bg_loop(cls):
        if cls._bg_loop is not None and cls._bg_loop.is_running():
            return
        cls._bg_loop = asyncio.new_event_loop()
        cls._bg_thread = threading.Thread(
            target=cls._bg_loop.run_forever, daemon=True, name="async-bg"
        )
        cls._bg_thread.start()

    @classmethod
    def get_bg_loop(cls) -> asyncio.AbstractEventLoop:
        cls._ensure_bg_loop()
        return cls._bg_loop

    @classmethod
    def get_image_pool(cls) -> ThreadPoolExecutor:
        if cls._image_pool is None:
            cls._image_pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="img")
        return cls._image_pool

    # ------------------------------------------------------------------
    # Async helper
    # ------------------------------------------------------------------

    def run_async(self, coro, callback: Optional[Callable] = None, error_callback: Optional[Callable] = None):
        """Run a coroutine on the shared background event loop."""
        loop = self.get_bg_loop()

        async def _wrapper():
            try:
                result = await coro
                if callback:
                    self.after(0, lambda r=result: callback(r))
            except Exception as e:
                if error_callback:
                    self.after(0, lambda err=e: error_callback(err))
                else:
                    print(f"[App] Async error: {e}")

        asyncio.run_coroutine_threadsafe(_wrapper(), loop)

    def on_closing(self):
        loop = self._bg_loop

        if loop and loop.is_running():
            async def _cleanup():
                try:
                    from core.utils import http_helper
                    await http_helper.close()
                except Exception:
                    pass

            future = asyncio.run_coroutine_threadsafe(_cleanup(), loop)
            try:
                future.result(timeout=2)
            except Exception:
                pass
            loop.call_soon_threadsafe(loop.stop)

        if self._image_pool:
            self._image_pool.shutdown(wait=False)

        self.destroy()
