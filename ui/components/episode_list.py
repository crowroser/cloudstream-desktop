"""
EpisodeList — displays a list of episodes grouped by season with selection support.
Supports thumbnails, batch loading, and bulk download.
"""
from __future__ import annotations
import io
import threading
from typing import List, Optional, Callable, Dict

import customtkinter as ctk
from PIL import Image

from core.models import Episode, SeasonData

OnEpisodeAction = Optional[Callable[[Episode], None]]

_THUMB_W, _THUMB_H = 80, 50
_BATCH_SIZE = 20


class EpisodeListView(ctk.CTkFrame):
    """
    Shows season tabs + episode rows.
    on_episode_click(episode) is called when an episode is selected.
    """

    def __init__(
        self,
        parent,
        episodes: List[Episode],
        season_names: Optional[List[SeasonData]] = None,
        on_episode_click: OnEpisodeAction = None,
        on_episode_download: OnEpisodeAction = None,
        on_download_all: Optional[Callable[[List[Episode]], None]] = None,
        fallback_poster: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.episodes = episodes
        self.season_names = season_names or []
        self.on_episode_click = on_episode_click
        self.on_episode_download = on_episode_download
        self.on_download_all = on_download_all
        self.fallback_poster = fallback_poster
        self._current_season: Optional[int] = None
        self._build()

    def _build(self):
        seasons: Dict[Optional[int], List[Episode]] = {}
        for ep in self.episodes:
            key = ep.season
            if key not in seasons:
                seasons[key] = []
            seasons[key].append(ep)

        sorted_seasons = sorted(seasons.keys(), key=lambda x: x or 0)

        if len(sorted_seasons) > 1:
            self._build_season_tabs(seasons, sorted_seasons)
        else:
            key = sorted_seasons[0] if sorted_seasons else None
            eps = seasons.get(key, [])
            self._build_episode_container(self, eps)

    def _build_season_tabs(self, seasons, sorted_seasons):
        tab_frame = ctk.CTkFrame(self, fg_color=("gray90", "gray20"), corner_radius=8)
        tab_frame.pack(fill="x", padx=4, pady=(0, 4))

        self._tab_buttons: Dict = {}
        self._season_content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._season_content_frame.pack(fill="both", expand=True)

        for season_num in sorted_seasons:
            label = self._get_season_name(season_num)
            btn = ctk.CTkButton(
                tab_frame,
                text=label,
                width=90,
                height=28,
                font=ctk.CTkFont(size=12),
                fg_color="transparent",
                hover_color=("gray75", "gray35"),
                command=lambda sn=season_num: self._show_season(sn, seasons),
            )
            btn.pack(side="left", padx=4, pady=4)
            self._tab_buttons[season_num] = btn

        if sorted_seasons:
            self._show_season(sorted_seasons[0], seasons)

    def _show_season(self, season_num, seasons):
        for widget in self._season_content_frame.winfo_children():
            widget.destroy()

        for sn, btn in self._tab_buttons.items():
            if sn == season_num:
                btn.configure(fg_color=("gray60", "gray50"))
            else:
                btn.configure(fg_color="transparent")

        self._current_season = season_num
        episodes = seasons.get(season_num, [])
        self._build_episode_container(self._season_content_frame, episodes)

    def _build_episode_container(self, parent, episodes: List[Episode]):
        toolbar = ctk.CTkFrame(parent, fg_color="transparent")
        toolbar.pack(fill="x", padx=4, pady=(2, 4))

        ctk.CTkLabel(
            toolbar,
            text=f"{len(episodes)} bölüm",
            font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray60"),
        ).pack(side="left", padx=4)

        if self.on_download_all and episodes:
            ctk.CTkButton(
                toolbar,
                text="⬇ Tümünü İndir",
                width=120, height=28,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color=("#4caf50", "#2e7d32"),
                hover_color=("#388e3c", "#1b5e20"),
                command=lambda eps=episodes: self.on_download_all(eps),
            ).pack(side="right", padx=4)

        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent", height=340)
        scroll.pack(fill="both", expand=True)

        self._pending_eps = episodes
        self._ep_scroll = scroll
        self._ep_batch_idx = 0
        self._place_episode_batch()

    def _place_episode_batch(self):
        start = self._ep_batch_idx
        end = min(start + _BATCH_SIZE, len(self._pending_eps))
        for i in range(start, end):
            ep = self._pending_eps[i]
            row = EpisodeRow(
                self._ep_scroll,
                episode=ep,
                on_click=self.on_episode_click,
                on_download=self.on_episode_download,
                fallback_poster=self.fallback_poster,
            )
            row.pack(fill="x", padx=4, pady=2)
        self._ep_batch_idx = end
        if end < len(self._pending_eps):
            self.after(16, self._place_episode_batch)

    def _get_season_name(self, season_num: Optional[int]) -> str:
        if season_num is None:
            return "Episodes"
        for sn in self.season_names:
            if sn.season == season_num:
                return sn.display_name()
        return f"Season {season_num}"


class EpisodeRow(ctk.CTkFrame):
    """Single episode row with thumbnail, play + download buttons."""

    _image_refs: List = []

    def __init__(
        self,
        parent,
        episode: Episode,
        on_click: OnEpisodeAction = None,
        on_download: OnEpisodeAction = None,
        fallback_poster: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(
            parent,
            fg_color=("gray85", "gray22"),
            corner_radius=6,
            height=56,
            **kwargs,
        )
        self.episode = episode
        self.on_click = on_click
        self.on_download = on_download
        self._fallback_poster = fallback_poster
        self.pack_propagate(False)
        self._build()

    def _build(self):
        self.configure(cursor="hand2")

        thumb_url = self.episode.poster_url or self._fallback_poster

        self._thumb_label = ctk.CTkLabel(
            self, text="", width=_THUMB_W, height=_THUMB_H,
            fg_color=("gray70", "gray28"), corner_radius=4,
        )
        self._thumb_label.pack(side="left", padx=(6, 4), pady=3)

        if thumb_url:
            self._load_thumb_async(thumb_url)

        ep_label = self.episode.display_name()
        ctk.CTkLabel(
            self,
            text=ep_label,
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).pack(side="left", padx=(4, 4), pady=8)

        if self.episode.description:
            desc = self.episode.description
            if len(desc) > 60:
                desc = desc[:60] + "..."
            ctk.CTkLabel(
                self,
                text=desc,
                font=ctk.CTkFont(size=11),
                text_color=("gray50", "gray60"),
                anchor="w",
            ).pack(side="left", padx=4, pady=8, fill="x", expand=True)

        if self.episode.run_time:
            ctk.CTkLabel(
                self,
                text=f"{self.episode.run_time}m",
                font=ctk.CTkFont(size=11),
                text_color=("gray50", "gray60"),
                width=40,
            ).pack(side="right", padx=4)

        if self.on_download:
            ctk.CTkButton(
                self,
                text="⬇",
                width=36, height=28,
                font=ctk.CTkFont(size=13),
                fg_color=("#4caf50", "#2e7d32"),
                hover_color=("#388e3c", "#1b5e20"),
                command=self._handle_download,
            ).pack(side="right", padx=(0, 4), pady=4)

        ctk.CTkButton(
            self,
            text="▶",
            width=36, height=28,
            font=ctk.CTkFont(size=13),
            fg_color="#1e88e5",
            hover_color="#1565c0",
            command=self._handle_click,
        ).pack(side="right", padx=(8, 4), pady=4)

        self.bind("<Button-1>", self._handle_click)

    def _load_thumb_async(self, url):
        from ui.app import CloudStreamApp
        CloudStreamApp.get_image_pool().submit(self._fetch_thumb, url)

    def _fetch_thumb(self, url):
        try:
            from ui.components.media_card import _cache_get, _cache_put
            import httpx
            img = _cache_get(url)
            if img is None:
                resp = httpx.get(url, timeout=8, follow_redirects=True)
                resp.raise_for_status()
                img = Image.open(io.BytesIO(resp.content)).convert("RGB")
                _cache_put(url, img)
            thumb = img.resize((_THUMB_W, _THUMB_H), Image.LANCZOS)
            ctk_img = ctk.CTkImage(light_image=thumb, dark_image=thumb,
                                   size=(_THUMB_W, _THUMB_H))
            EpisodeRow._image_refs.append(ctk_img)

            def _apply():
                try:
                    if self.winfo_exists() and self._thumb_label.winfo_exists():
                        self._thumb_label.configure(image=ctk_img, text="")
                except Exception:
                    pass

            self.after(0, _apply)
        except Exception:
            pass

    def _handle_click(self, event=None):
        if self.on_click:
            self.on_click(self.episode)

    def _handle_download(self):
        if self.on_download:
            self.on_download(self.episode)


class AnimeEpisodeList(ctk.CTkFrame):
    """Episode list with Dubbed/Subbed tab selection."""

    def __init__(
        self,
        parent,
        episodes_dict: Dict[str, List[Episode]],
        on_episode_click: OnEpisodeAction = None,
        on_episode_download: OnEpisodeAction = None,
        on_download_all: Optional[Callable[[List[Episode]], None]] = None,
        fallback_poster: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.episodes_dict = episodes_dict
        self.on_episode_click = on_episode_click
        self.on_episode_download = on_episode_download
        self.on_download_all = on_download_all
        self.fallback_poster = fallback_poster
        self._build()

    def _build(self):
        if not self.episodes_dict:
            ctk.CTkLabel(self, text="No episodes available.").pack(pady=20)
            return

        dub_keys = list(self.episodes_dict.keys())

        if len(dub_keys) > 1:
            tab_frame = ctk.CTkFrame(self, fg_color="transparent")
            tab_frame.pack(fill="x", pady=(0, 4))
            for key in dub_keys:
                ctk.CTkButton(
                    tab_frame,
                    text=key,
                    width=80, height=28,
                    command=lambda k=key: self._show_dub(k),
                ).pack(side="left", padx=4)

        self._content = ctk.CTkFrame(self, fg_color="transparent")
        self._content.pack(fill="both", expand=True)
        self._show_dub(dub_keys[0])

    def _show_dub(self, key: str):
        for w in self._content.winfo_children():
            w.destroy()
        episodes = self.episodes_dict.get(key, [])
        EpisodeListView(
            self._content,
            episodes=episodes,
            on_episode_click=self.on_episode_click,
            on_episode_download=self.on_episode_download,
            on_download_all=self.on_download_all,
            fallback_poster=self.fallback_poster,
        ).pack(fill="both", expand=True)
