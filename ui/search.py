"""
SearchPage — search across all providers with filters.
"""
from __future__ import annotations
from typing import TYPE_CHECKING, List, Optional

import customtkinter as ctk

from core.models import SearchResponse, TvType
from core.api_holder import APIHolder
from core.i18n import tr
from ui.components.media_card import MediaCard

if TYPE_CHECKING:
    from ui.app import CloudStreamApp

FILTER_TYPES = ["All Types", "Movie", "TvSeries", "Anime", "AsianDrama", "Cartoon", "Documentary"]


_MAX_SEARCH_RESULTS = 120


class SearchPage(ctk.CTkFrame):
    def __init__(self, parent, app: "CloudStreamApp", **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.app = app
        self._results: List[SearchResponse] = []
        self._search_jobs = 0
        self._search_debounce_id = None
        self._build()

    def _build(self):
        # Search header
        header = ctk.CTkFrame(self, height=60, fg_color=("gray88", "gray14"), corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header,
            text=tr("Search"),
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(side="left", padx=16, pady=14)

        # Search box
        search_frame = ctk.CTkFrame(header, fg_color="transparent")
        search_frame.pack(side="left", fill="x", expand=True, padx=(8, 0), pady=10)

        self.search_entry = ctk.CTkEntry(
            search_frame,
            placeholder_text=tr("Search movies, series, anime..."),
            font=ctk.CTkFont(size=14),
            height=36,
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.search_entry.bind("<Return>", lambda e: self._do_search())

        ctk.CTkButton(
            search_frame,
            text=tr("Search"),
            width=80, height=36,
            command=self._do_search,
        ).pack(side="left")

        # Filter bar
        filter_bar = ctk.CTkFrame(self, fg_color=("gray83", "gray17"), height=42, corner_radius=0)
        filter_bar.pack(fill="x")
        filter_bar.pack_propagate(False)

        ctk.CTkLabel(filter_bar, text=tr("Type:"), font=ctk.CTkFont(size=12)).pack(
            side="left", padx=(12, 4), pady=8
        )
        self.type_filter = ctk.CTkOptionMenu(
            filter_bar,
            values=[tr(t) for t in FILTER_TYPES],
            width=140, height=28,
            command=lambda _: self._apply_filter(),
        )
        self.type_filter.pack(side="left", padx=4, pady=6)

        ctk.CTkLabel(filter_bar, text=tr("Provider:"), font=ctk.CTkFont(size=12)).pack(
            side="left", padx=(16, 4)
        )
        self.provider_filter = ctk.CTkOptionMenu(
            filter_bar,
            values=[tr("All Providers")],
            width=170, height=28,
            command=lambda _: self._do_search(),
        )
        self.provider_filter.pack(side="left", padx=4, pady=6)

        self.result_count = ctk.CTkLabel(
            filter_bar,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray60"),
        )
        self.result_count.pack(side="right", padx=12)

        # Results grid
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True)

        self.state_label = ctk.CTkLabel(
            self.scroll,
            text=tr("Type something to search..."),
            font=ctk.CTkFont(size=16),
            text_color=("gray50", "gray55"),
        )
        self.state_label.pack(pady=80)

        # Update provider list
        self._refresh_providers()
        APIHolder.on_plugins_loaded(self._refresh_providers)

    def _refresh_providers(self):
        names = [tr("All Providers")] + [p.name for p in APIHolder.apis]
        self.after(0, lambda: self.provider_filter.configure(values=names))

    def _do_search(self):
        query = self.search_entry.get().strip()
        if not query:
            return

        # Save to history
        from data.database import Database
        Database.add_search(query)

        self._clear_results()
        self._ensure_state_label()
        self.state_label.configure(text=f'"{query}" aranıyor...')
        self.state_label.pack(pady=80)

        # Determine which providers to search
        selected = self.provider_filter.get()
        if selected == tr("All Providers"):
            providers = APIHolder.apis
        else:
            providers = [p for p in APIHolder.apis if p.name == selected]

        if not providers:
            self.state_label.configure(text=tr("No providers loaded. Add plugins first."))
            return

        self._search_jobs = len(providers)
        self._results = []

        for provider in providers:
            self.app.run_async(
                provider.search(query),
                callback=lambda results, prov=provider: self._on_results(results, prov),
                error_callback=lambda e, prov=provider: self._on_error(e, prov),
            )

    def _on_results(self, results, provider):
        if results:
            for r in results:
                if len(self._results) >= _MAX_SEARCH_RESULTS:
                    break
                if r not in self._results:
                    self._results.append(r)
        self._search_jobs = max(0, self._search_jobs - 1)
        if self._search_jobs == 0:
            self._display_results()

    def _on_error(self, error, provider):
        print(f"[Search] Error from {provider.name}: {error}")
        self._search_jobs = max(0, self._search_jobs - 1)
        if self._search_jobs == 0:
            self._display_results()

    _BATCH_SIZE = 12

    def _display_results(self):
        self._clear_results()
        results = self._apply_filter_to(self._results)

        if not results:
            self._ensure_state_label()
            self.state_label.configure(text=tr("No results found."))
            self.state_label.pack(pady=80)
            self.result_count.configure(text="0 sonuç")
            return

        self.result_count.configure(text=f"{len(results)} sonuç")

        grid = ctk.CTkFrame(self.scroll, fg_color="transparent")
        grid.pack(fill="both", padx=8, pady=8)
        self._result_grid = grid
        self._pending_results = results
        self._batch_index = 0
        self._place_next_batch()

    def _place_next_batch(self):
        grid = getattr(self, "_result_grid", None)
        results = getattr(self, "_pending_results", [])
        if grid is None or not results:
            return
        start = self._batch_index
        end = min(start + self._BATCH_SIZE, len(results))
        cols = 6
        for i in range(start, end):
            card = MediaCard(
                grid,
                result=results[i],
                on_click=self.app.navigate_to_result,
            )
            card.grid(row=i // cols, column=i % cols, padx=6, pady=6, sticky="n")
        self._batch_index = end
        if end < len(results):
            self.after(16, self._place_next_batch)

    def _apply_filter(self):
        self._display_results()

    def _apply_filter_to(self, results: List[SearchResponse]) -> List[SearchResponse]:
        type_str = self.type_filter.get()
        if type_str == "All Types":
            return results
        try:
            tv_type = TvType(type_str)
            return [r for r in results if r.type == tv_type]
        except ValueError:
            return results

    def _ensure_state_label(self):
        """state_label yok edildiyse yeniden olustur."""
        try:
            self.state_label.winfo_exists()
        except (AttributeError, Exception):
            self.state_label = None
        if self.state_label is None or not self.state_label.winfo_exists():
            self.state_label = ctk.CTkLabel(
                self.scroll,
                text="",
                font=ctk.CTkFont(size=16),
                text_color=("gray50", "gray55"),
            )

    def _clear_results(self):
        self._pending_results = []
        self._result_grid = None
        for widget in self.scroll.winfo_children():
            widget.destroy()
        self.state_label = None

    def navigate(self, query: str = ""):
        if query:
            self.search_entry.delete(0, "end")
            self.search_entry.insert(0, query)
            self._do_search()
