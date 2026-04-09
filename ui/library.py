"""
LibraryPage — bookmarks and watch history.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

import customtkinter as ctk

from data.database import Database
from core.i18n import tr
from ui.components.media_card import MediaCard
from core.models import SearchResponse, TvType

if TYPE_CHECKING:
    from ui.app import CloudStreamApp


class LibraryPage(ctk.CTkFrame):
    def __init__(self, parent, app: "CloudStreamApp", **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.app = app
        self._build()

    def _build(self):
        header = ctk.CTkFrame(self, height=52, fg_color=("gray88", "gray14"), corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header, text=tr("Library"),
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(side="left", padx=16, pady=12)

        # Tabs
        self.tab_view = ctk.CTkTabview(self, height=40)
        self.tab_view.pack(fill="both", expand=True, padx=8, pady=8)

        self.tab_view.add(tr("Bookmarks"))
        self.tab_view.add(tr("Watch History"))
        self.tab_view.add(tr("Continue Watching"))

        self._build_bookmarks_tab()
        self._build_history_tab()
        self._build_continue_tab()

    def _build_bookmarks_tab(self):
        tab = self.tab_view.tab(tr("Bookmarks"))
        btn_bar = ctk.CTkFrame(tab, fg_color="transparent")
        btn_bar.pack(fill="x", pady=4)

        ctk.CTkButton(
            btn_bar, text=tr("Refresh"), width=80, height=28,
            command=self._refresh_bookmarks,
        ).pack(side="left", padx=4)

        self.bookmarks_scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self.bookmarks_scroll.pack(fill="both", expand=True)

        self._refresh_bookmarks()

    def _refresh_bookmarks(self):
        for w in self.bookmarks_scroll.winfo_children():
            w.destroy()

        entries = Database.get_bookmarks()
        if not entries:
            ctk.CTkLabel(
                self.bookmarks_scroll,
                text=tr("No bookmarks yet.\nBrowse content and tap ☆ to bookmark."),
                font=ctk.CTkFont(size=14),
                text_color=("gray50", "gray55"),
            ).pack(pady=60)
            return

        grid = ctk.CTkFrame(self.bookmarks_scroll, fg_color="transparent")
        grid.pack(fill="x", padx=8, pady=8)

        cols = 7
        for i, entry in enumerate(entries):
            result = SearchResponse(
                name=entry.name,
                url=entry.url,
                api_name=entry.api_name,
                type=entry.type,
                poster_url=entry.poster_url,
            )
            card = MediaCard(
                grid, result=result,
                on_click=self.app.navigate_to_result,
            )
            card.grid(row=i // cols, column=i % cols, padx=6, pady=6, sticky="n")

    def _build_history_tab(self):
        tab = self.tab_view.tab(tr("Watch History"))
        btn_bar = ctk.CTkFrame(tab, fg_color="transparent")
        btn_bar.pack(fill="x", pady=4)

        ctk.CTkButton(
            btn_bar, text=tr("Refresh"), width=80, height=28,
            command=self._refresh_history,
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            btn_bar, text=tr("Clear All"), width=90, height=28,
            fg_color=("gray70", "gray25"),
            command=self._clear_history,
        ).pack(side="left", padx=4)

        self.history_scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self.history_scroll.pack(fill="both", expand=True)

        self._refresh_history()

    def _refresh_history(self):
        for w in self.history_scroll.winfo_children():
            w.destroy()

        entries = Database.get_watch_history(limit=100)
        if not entries:
            ctk.CTkLabel(
                self.history_scroll,
                text=tr("No watch history yet."),
                font=ctk.CTkFont(size=14),
                text_color=("gray50", "gray55"),
            ).pack(pady=60)
            return

        for entry in entries:
            row = ctk.CTkFrame(
                self.history_scroll,
                fg_color=("gray85", "gray22"),
                corner_radius=8, height=52,
            )
            row.pack(fill="x", padx=8, pady=2)
            row.pack_propagate(False)

            ctk.CTkLabel(
                row, text=entry.name,
                font=ctk.CTkFont(size=13, weight="bold"),
                anchor="w",
            ).pack(side="left", padx=12, pady=4)

            ep_text = ""
            if entry.season and entry.episode:
                ep_text = f"S{entry.season:02d}E{entry.episode:02d}"
            elif entry.episode:
                ep_text = f"Ep {entry.episode}"
            if ep_text:
                ctk.CTkLabel(
                    row, text=ep_text,
                    font=ctk.CTkFont(size=11),
                    text_color=("gray50", "gray60"),
                ).pack(side="left", padx=4)

            if entry.duration > 0:
                progress = min(entry.position / entry.duration, 1.0)
                bar = ctk.CTkProgressBar(row, width=80, height=6)
                bar.set(progress)
                bar.pack(side="right", padx=12)

    def _clear_history(self):
        Database.clear_watch_history()
        self._refresh_history()

    def _build_continue_tab(self):
        tab = self.tab_view.tab(tr("Continue Watching"))
        entries = Database.get_watch_history(limit=20)
        in_progress = [e for e in entries if 0 < e.position < e.duration * 0.95]

        if not in_progress:
            ctk.CTkLabel(
                tab,
                text=tr("Nothing in progress."),
                font=ctk.CTkFont(size=14),
                text_color=("gray50", "gray55"),
            ).pack(pady=60)
            return

        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        cols = 6
        grid = ctk.CTkFrame(scroll, fg_color="transparent")
        grid.pack(fill="x", padx=8, pady=8)

        for i, entry in enumerate(in_progress):
            result = SearchResponse(
                name=entry.name, url=entry.url,
                api_name=entry.api_name, poster_url=entry.poster_url,
            )
            MediaCard(
                grid, result=result,
                on_click=self.app.navigate_to_result,
            ).grid(row=i // cols, column=i % cols, padx=6, pady=6, sticky="n")
