"""
ResultPage — content detail view (poster, info, episodes, actors, recommendations).
"""
from __future__ import annotations
import asyncio
import time
from typing import TYPE_CHECKING, List, Optional

import customtkinter as ctk
from PIL import Image
import io, threading

from core.models import (
    SearchResponse, LoadResponse, MovieLoadResponse,
    TvSeriesLoadResponse, AnimeLoadResponse, Episode,
    ExtractorLink, SubtitleFile, TvType
)
from core.api_holder import APIHolder

if TYPE_CHECKING:
    from ui.app import CloudStreamApp


class ResultPage(ctk.CTkFrame):
    def __init__(self, parent, app: "CloudStreamApp", **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.app = app
        self._current_result: Optional[SearchResponse] = None
        self._load_response: Optional[LoadResponse] = None
        self._links: List[ExtractorLink] = []
        self._subtitles: List[SubtitleFile] = []
        self._build_skeleton()

    def _build_skeleton(self):
        # Back button bar
        top_bar = ctk.CTkFrame(self, height=48, fg_color=("gray88", "gray15"), corner_radius=0)
        top_bar.pack(fill="x")
        top_bar.pack_propagate(False)

        ctk.CTkButton(
            top_bar,
            text="← Back",
            width=80, height=32,
            fg_color="transparent",
            command=self.app.go_back,
        ).pack(side="left", padx=8, pady=8)

        self.page_title = ctk.CTkLabel(
            top_bar,
            text="",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        self.page_title.pack(side="left", padx=8)

        # Main scroll
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True)

        self.content_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True, padx=16, pady=8)

    def load_result(self, result: SearchResponse):
        self._current_result = result
        self._load_response = None
        self._links = []
        self._subtitles = []
        self.page_title.configure(text=result.name)

        # Clear previous content
        for w in self.content_frame.winfo_children():
            w.destroy()

        # Show loading
        self._loading_label = ctk.CTkLabel(
            self.content_frame,
            text="Loading...",
            font=ctk.CTkFont(size=16),
            text_color=("gray50", "gray55"),
        )
        self._loading_label.pack(pady=60)

        # Find API
        api = APIHolder.get_api_by_name(result.api_name)
        if api is None:
            self._loading_label.configure(text=f"Provider '{result.api_name}' not found.")
            return

        self.app.run_async(
            api.load(result.url),
            callback=self._on_loaded,
            error_callback=self._on_error,
        )

    def _on_loaded(self, response: Optional[LoadResponse]):
        if response is None:
            self._loading_label.configure(text="Failed to load content.")
            return
        self._load_response = response
        for w in self.content_frame.winfo_children():
            w.destroy()
        self._render(response)

    def _on_error(self, error):
        self._loading_label.configure(text=f"Error: {error}")

    def _render(self, resp: LoadResponse):
        # Hero section (poster + info side by side)
        hero = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        hero.pack(fill="x", pady=(0, 16))

        # Poster
        poster_frame = ctk.CTkFrame(
            hero, width=180, height=270,
            fg_color=("gray80", "gray20"), corner_radius=10
        )
        poster_frame.pack(side="left", padx=(0, 20))
        poster_frame.pack_propagate(False)

        self._poster_label = ctk.CTkLabel(poster_frame, text="")
        self._poster_label.place(relx=0.5, rely=0.5, anchor="center")
        self._load_poster(resp.poster_url)

        # Info column
        info = ctk.CTkFrame(hero, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(
            info,
            text=resp.name,
            font=ctk.CTkFont(size=24, weight="bold"),
            wraplength=600, justify="left",
        ).pack(anchor="w")

        # Meta row
        meta_row = ctk.CTkFrame(info, fg_color="transparent")
        meta_row.pack(anchor="w", pady=4)
        meta_parts = []
        if resp.year:
            meta_parts.append(str(resp.year))
        if resp.duration:
            meta_parts.append(f"{resp.duration}m")
        if resp.score is not None:
            meta_parts.append(f"★ {resp.score:.1f}")
        if resp.content_rating:
            meta_parts.append(resp.content_rating)
        for part in meta_parts:
            ctk.CTkLabel(
                meta_row,
                text=part,
                fg_color=("gray75", "gray30"),
                corner_radius=4,
                font=ctk.CTkFont(size=12),
                padx=6, pady=2,
            ).pack(side="left", padx=3)

        # Tags
        if resp.tags:
            tag_row = ctk.CTkFrame(info, fg_color="transparent")
            tag_row.pack(anchor="w", pady=2)
            for tag in resp.tags[:8]:
                ctk.CTkLabel(
                    tag_row, text=tag,
                    fg_color=("#1e88e5", "#1565c0"),
                    text_color="white",
                    corner_radius=4,
                    font=ctk.CTkFont(size=11),
                    padx=6, pady=2,
                ).pack(side="left", padx=2)

        # Plot
        if resp.plot:
            ctk.CTkLabel(
                info,
                text=resp.plot,
                font=ctk.CTkFont(size=12),
                wraplength=580,
                justify="left",
                text_color=("gray30", "gray70"),
            ).pack(anchor="w", pady=(6, 0))

        # Action buttons
        btn_row = ctk.CTkFrame(info, fg_color="transparent")
        btn_row.pack(anchor="w", pady=12)

        self.watch_btn = ctk.CTkButton(
            btn_row,
            text="▶  İzle",
            width=120, height=38,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#1e88e5",
            hover_color="#1565c0",
            command=self._on_watch_clicked,
        )
        self.watch_btn.pack(side="left", padx=(0, 8))

        self.bookmark_btn = ctk.CTkButton(
            btn_row,
            text="☆ Bookmark",
            width=110, height=38,
            fg_color=("gray75", "gray30"),
            hover_color=("gray65", "gray40"),
            command=self._toggle_bookmark,
        )
        self.bookmark_btn.pack(side="left", padx=4)
        self._update_bookmark_btn()

        # Trailer button
        if resp.trailers:
            ctk.CTkButton(
                btn_row,
                text="▶ Trailer",
                width=90, height=38,
                fg_color=("gray70", "gray25"),
                command=lambda: self._play_trailer(resp.trailers[0]),
            ).pack(side="left", padx=4)

        # Separator
        ctk.CTkFrame(self.content_frame, height=1, fg_color=("gray70", "gray30")).pack(
            fill="x", pady=8
        )

        # Episodes / Movie play
        if isinstance(resp, TvSeriesLoadResponse):
            self._render_episodes_section(resp)
        elif isinstance(resp, AnimeLoadResponse):
            self._render_anime_episodes(resp)
        elif isinstance(resp, MovieLoadResponse):
            self._render_movie_links(resp)

        # Actors
        if resp.actors:
            self._render_actors(resp.actors)

        # Recommendations
        if resp.recommendations:
            self._render_recommendations(resp.recommendations)

    # ------------------------------------------------------------------
    # Sub-sections
    # ------------------------------------------------------------------

    def _render_episodes_section(self, resp: TvSeriesLoadResponse):
        ctk.CTkLabel(
            self.content_frame,
            text="Episodes",
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w",
        ).pack(anchor="w", pady=(4, 4))

        from ui.components.episode_list import EpisodeListView
        EpisodeListView(
            self.content_frame,
            episodes=resp.episodes,
            season_names=resp.season_names,
            on_episode_click=self._on_episode_click,
            on_episode_download=self._on_episode_download,
            on_download_all=self._on_download_all,
            fallback_poster=resp.poster_url,
        ).pack(fill="x")

    def _render_anime_episodes(self, resp: AnimeLoadResponse):
        ctk.CTkLabel(
            self.content_frame,
            text="Episodes",
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w",
        ).pack(anchor="w", pady=(4, 4))

        from ui.components.episode_list import AnimeEpisodeList
        AnimeEpisodeList(
            self.content_frame,
            episodes_dict=resp.episodes,
            on_episode_click=self._on_episode_click,
            on_episode_download=self._on_episode_download,
            on_download_all=self._on_download_all,
            fallback_poster=resp.poster_url,
        ).pack(fill="x")

    def _render_movie_links(self, resp: MovieLoadResponse):
        if resp.data_url:
            self._load_links_for_data(resp.data_url)

    def _render_actors(self, actors):
        ctk.CTkLabel(
            self.content_frame,
            text="Cast",
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w",
        ).pack(anchor="w", pady=(12, 4))

        scroll = ctk.CTkScrollableFrame(
            self.content_frame, orientation="horizontal", height=100, fg_color="transparent"
        )
        scroll.pack(fill="x")

        for actor_data in actors[:20]:
            actor = actor_data.actor
            card = ctk.CTkFrame(scroll, width=80, height=90, fg_color=("gray82", "gray22"), corner_radius=8)
            card.pack(side="left", padx=4)
            card.pack_propagate(False)
            ctk.CTkLabel(card, text=actor.name[:14], font=ctk.CTkFont(size=10), wraplength=74).place(
                relx=0.5, rely=0.75, anchor="center"
            )

    def _render_recommendations(self, recs):
        ctk.CTkLabel(
            self.content_frame,
            text="More Like This",
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w",
        ).pack(anchor="w", pady=(12, 4))

        from core.models import HomePageList
        from ui.components.horizontal_scroll import HorizontalScrollRow
        hl = HomePageList(name="", list=recs)
        HorizontalScrollRow(
            self.content_frame,
            home_page_list=hl,
            on_card_click=self.load_result,
        ).pack(fill="x")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_watch_clicked(self):
        resp = self._load_response
        if resp is None:
            return
        if isinstance(resp, MovieLoadResponse) and resp.data_url:
            self._load_links_for_data(resp.data_url, auto_play=True)
        elif isinstance(resp, (TvSeriesLoadResponse, AnimeLoadResponse)):
            # Try to play first available episode
            eps = []
            if isinstance(resp, TvSeriesLoadResponse):
                eps = resp.episodes
            elif isinstance(resp, AnimeLoadResponse):
                for v in resp.episodes.values():
                    eps = v
                    break
            if eps:
                self._on_episode_click(eps[0])

    def _collect_all_episodes(self) -> List[Episode]:
        """Flatten all episodes from the current load response."""
        resp = self._load_response
        if isinstance(resp, TvSeriesLoadResponse):
            return list(resp.episodes)
        elif isinstance(resp, AnimeLoadResponse):
            flat: List[Episode] = []
            for eps in resp.episodes.values():
                flat.extend(eps)
            return flat
        return []

    def _on_episode_click(self, episode: Episode):
        api = APIHolder.get_api_by_name(self._current_result.api_name)
        if api is None:
            self.app.set_status("Sağlayıcı bulunamadı.")
            return
        self.watch_btn.configure(state="disabled", text="Yükleniyor...")

        all_eps = self._collect_all_episodes()
        links: List[ExtractorLink] = []
        subs: List[SubtitleFile] = []

        async def _load():
            try:
                await api.load_links(
                    episode.data,
                    is_casting=False,
                    callback=links.append,
                    subtitle_callback=subs.append,
                )
            except Exception as exc:
                print(f"[ResultPage] load_links error: {exc}")
            return links, subs

        def _done(result):
            lks, ss = result
            self.watch_btn.configure(state="normal", text="▶  İzle")
            if not lks:
                self.app.set_status("Oynatılabilir bağlantı bulunamadı.")
                return
            r = self._current_result
            self.app.navigate_to_player(
                links=lks,
                subtitles=ss,
                title=r.name,
                episode=episode,
                content_url=r.url,
                api_name=r.api_name,
                poster_url=r.poster_url or "",
                all_episodes=all_eps,
            )

        def _err(e):
            print(f"[ResultPage] load_links exception: {e}")
            self.watch_btn.configure(state="normal", text="▶  İzle")
            self.app.set_status(f"Hata: {e}")

        self.app.run_async(_load(), callback=_done, error_callback=_err)

    def _on_episode_download(self, episode: Episode):
        """Extract links then start downloading the best quality."""
        api = APIHolder.get_api_by_name(self._current_result.api_name)
        if api is None:
            self.app.set_status("Sağlayıcı bulunamadı.")
            return
        self.app.set_status(f"Bağlantılar alınıyor: {episode.display_name()}...")

        links: List[ExtractorLink] = []

        async def _load():
            try:
                await api.load_links(
                    episode.data,
                    is_casting=False,
                    callback=links.append,
                    subtitle_callback=lambda _: None,
                )
            except Exception as exc:
                print(f"[ResultPage] download load_links error: {exc}")
            return links

        def _done(result):
            lks = result
            if not lks:
                self.app.set_status("İndirilebilir bağlantı bulunamadı.")
                return
            best = max(lks, key=lambda l: l.quality or 0)
            from ui.downloads import DownloadManager
            title = self._current_result.name if self._current_result else "Video"
            DownloadManager.start_download(
                link=best,
                title=title,
                episode_name=episode.display_name(),
            )
            self.app.set_status(
                f"İndirme başlatıldı: {episode.display_name()} ({best.quality}p)"
            )

        def _err(e):
            print(f"[ResultPage] download error: {e}")
            self.app.set_status(f"İndirme hatası: {e}")

        self.app.run_async(_load(), callback=_done, error_callback=_err)

    def _on_download_all(self, episodes: List[Episode]):
        """Queue download for all episodes sequentially."""
        api = APIHolder.get_api_by_name(self._current_result.api_name)
        if api is None:
            self.app.set_status("Sağlayıcı bulunamadı.")
            return
        total = len(episodes)
        self.app.set_status(f"Tümü indiriliyor: {total} bölüm...")
        self._dl_queue = list(episodes)
        self._dl_done = 0
        self._dl_total = total
        self._process_next_download()

    def _process_next_download(self):
        if not self._dl_queue:
            self.app.set_status(
                f"Tümü kuyruğa eklendi: {self._dl_total} bölüm"
            )
            return
        episode = self._dl_queue.pop(0)
        self._dl_done += 1
        self.app.set_status(
            f"Bağlantılar alınıyor ({self._dl_done}/{self._dl_total}): {episode.display_name()}..."
        )
        api = APIHolder.get_api_by_name(self._current_result.api_name)
        if api is None:
            return

        links: List[ExtractorLink] = []

        async def _load():
            try:
                await api.load_links(
                    episode.data, False, links.append, lambda _: None,
                )
            except Exception as exc:
                print(f"[ResultPage] download_all error: {exc}")
            return links

        def _done(result):
            lks = result
            if lks:
                best = max(lks, key=lambda l: l.quality or 0)
                from ui.downloads import DownloadManager
                title = self._current_result.name if self._current_result else "Video"
                DownloadManager.start_download(
                    link=best, title=title,
                    episode_name=episode.display_name(),
                )
            self.after(300, self._process_next_download)

        def _err(e):
            print(f"[ResultPage] download_all ep error: {e}")
            self.after(300, self._process_next_download)

        self.app.run_async(_load(), callback=_done, error_callback=_err)

    def _load_links_for_data(self, data: str, auto_play: bool = False):
        api = APIHolder.get_api_by_name(self._current_result.api_name)
        if api is None:
            self.app.set_status("Sağlayıcı bulunamadı.")
            return
        self.watch_btn.configure(state="disabled", text="Yükleniyor...")
        links: List[ExtractorLink] = []
        subs: List[SubtitleFile] = []

        async def _load():
            try:
                await api.load_links(data, False, links.append, subs.append)
            except Exception as exc:
                print(f"[ResultPage] load_links_for_data error: {exc}")
            return links, subs

        def _done(result):
            lks, ss = result
            self.watch_btn.configure(state="normal", text="▶  İzle")
            if auto_play and lks:
                r = self._current_result
                self.app.navigate_to_player(
                    lks, ss, r.name,
                    content_url=r.url, api_name=r.api_name,
                    poster_url=r.poster_url or "",
                )
            elif not lks:
                self.app.set_status("Oynatılabilir bağlantı bulunamadı.")

        def _err(e):
            print(f"[ResultPage] load_links_for_data exception: {e}")
            self.watch_btn.configure(state="normal", text="▶  İzle")
            self.app.set_status(f"Hata: {e}")

        self.app.run_async(_load(), callback=_done, error_callback=_err)

    def _toggle_bookmark(self):
        if self._current_result is None:
            return
        from data.database import Database
        from core.models import BookmarkEntry
        import time
        r = self._current_result
        if Database.is_bookmarked(r.url, r.api_name):
            Database.remove_bookmark(r.url, r.api_name)
        else:
            Database.add_bookmark(BookmarkEntry(
                url=r.url, api_name=r.api_name, name=r.name,
                type=r.type or TvType.Others,
                poster_url=r.poster_url, timestamp=int(time.time()),
            ))
        self._update_bookmark_btn()

    def _update_bookmark_btn(self):
        if self._current_result is None:
            return
        from data.database import Database
        bookmarked = Database.is_bookmarked(
            self._current_result.url, self._current_result.api_name
        )
        self.bookmark_btn.configure(
            text="★ Bookmarked" if bookmarked else "☆ Bookmark",
            fg_color=("#f57c00", "#e65100") if bookmarked else ("gray75", "gray30"),
        )

    def _play_trailer(self, trailer):
        link = ExtractorLink(
            source="Trailer", name="Trailer",
            url=trailer.extractor_url, quality=720,
        )
        r = self._current_result
        self.app.navigate_to_player(
            links=[link], title=f"{r.name} — Trailer",
            content_url=r.url, api_name=r.api_name,
            poster_url=r.poster_url or "",
        )

    def _load_poster(self, url: Optional[str]):
        if not url:
            return
        from ui.app import CloudStreamApp
        CloudStreamApp.get_image_pool().submit(self._fetch_poster, url)

    def _fetch_poster(self, url: str):
        try:
            from ui.components.media_card import _cache_get, _cache_put
            img = _cache_get(url)
            if img is None:
                import httpx
                resp = httpx.get(url, timeout=10, follow_redirects=True)
                img = Image.open(io.BytesIO(resp.content)).convert("RGB")
                _cache_put(url, img)
            poster = img.resize((176, 266), Image.LANCZOS)
            ctk_img = ctk.CTkImage(light_image=poster, dark_image=poster, size=(176, 266))
            self._poster_ref = ctk_img

            def _apply():
                try:
                    if self.winfo_exists() and self._poster_label.winfo_exists():
                        self._poster_label.configure(image=ctk_img, text="")
                except Exception:
                    pass

            self.after(0, _apply)
        except Exception:
            pass
