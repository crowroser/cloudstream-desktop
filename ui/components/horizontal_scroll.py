"""
HorizontalScrollRow — a labeled row of MediaCards that scrolls horizontally.
"""
from __future__ import annotations
from typing import List, Callable, Optional

import customtkinter as ctk

from core.models import SearchResponse, HomePageList
from ui.components.media_card import MediaCard


class HorizontalScrollRow(ctk.CTkFrame):
    """
    A labeled section with a horizontal row of MediaCards.
    Shows category name as header and cards in a scrollable row.
    """

    def __init__(
        self,
        parent,
        home_page_list: HomePageList,
        on_card_click: Optional[Callable[[SearchResponse], None]] = None,
        **kwargs,
    ):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.home_page_list = home_page_list
        self.on_card_click = on_card_click
        self._cards: List[MediaCard] = []
        self._build()

    _BATCH_SIZE = 8

    def _build(self):
        # Section header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=8, pady=(8, 2))

        ctk.CTkLabel(
            header,
            text=self.home_page_list.name,
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w",
        ).pack(side="left")

        self._scroll_frame = ctk.CTkScrollableFrame(
            self,
            orientation="horizontal",
            height=270,
            fg_color="transparent",
            scrollbar_button_color=("#888", "#555"),
            scrollbar_button_hover_color=("#aaa", "#777"),
        )
        self._scroll_frame.pack(fill="x", padx=8, pady=(0, 4))

        self._items = list(self.home_page_list.list)
        self._batch_idx = 0
        self._place_next_batch()

    def _place_next_batch(self):
        start = self._batch_idx
        end = min(start + self._BATCH_SIZE, len(self._items))
        for i in range(start, end):
            card = MediaCard(
                self._scroll_frame,
                result=self._items[i],
                on_click=self.on_card_click,
            )
            card.pack(side="left", padx=4, pady=4)
            self._cards.append(card)
        self._batch_idx = end
        if end < len(self._items):
            self.after(16, self._place_next_batch)

    def update_items(self, new_items: List[SearchResponse]) -> None:
        self.home_page_list.list.extend(new_items)
        # Refresh would require re-building; for simplicity add new cards only
        # (in practice you'd get the scroll_frame reference)


class LoadMoreButton(ctk.CTkButton):
    """Button that triggers loading the next page of a category."""

    def __init__(self, parent, on_click: Callable, **kwargs):
        super().__init__(
            parent,
            text="Load More",
            width=120,
            height=32,
            command=on_click,
            fg_color=("gray70", "gray30"),
            hover_color=("gray60", "gray40"),
            **kwargs,
        )
