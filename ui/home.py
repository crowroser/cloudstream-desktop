"""
HomePage — main screen showing selected provider's home page rows.
"""
from __future__ import annotations
from typing import TYPE_CHECKING, List, Optional

import customtkinter as ctk

from core.models import HomePageList, SearchResponse, MainPageRequest, ExtractorLink, SubtitleFile
from core.api_holder import APIHolder
from core.i18n import tr
from data.database import Database
from ui.components.horizontal_scroll import HorizontalScrollRow

if TYPE_CHECKING:
    from ui.app import CloudStreamApp


class HomePage(ctk.CTkFrame):
    def __init__(self, parent, app: "CloudStreamApp", **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.app = app
        self._loading = False
        self._pending_requests = 0
        self._refresh_scheduled_id = None
        self._build()
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

    def _build(self):
        header = ctk.CTkFrame(self, height=52, fg_color=("gray88", "gray14"), corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header,
            text=tr("Home"),
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(side="left", padx=16, pady=12)

        self.refresh_btn = ctk.CTkButton(
            header,
            text=tr("↻ Refresh"),
            width=100, height=32,
            command=lambda: self.refresh(force=True),
            fg_color="transparent",
            border_width=1,
            border_color=("gray60", "gray38"),
            text_color=("gray20", "gray90"),
        )
        self.refresh_btn.pack(side="right", padx=16, pady=10)

        self.provider_var = ctk.StringVar(value="")
        self.provider_menu = ctk.CTkOptionMenu(
            header,
            variable=self.provider_var,
            values=[tr("No providers")],
            width=200,
            command=self._on_provider_changed,
        )
        self.provider_menu.pack(side="right", padx=8, pady=10)

        self.scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color=("gray70", "gray40"),
        )
        self.scroll.pack(fill="both", expand=True)

        self._continue_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        self._continue_frame.pack(fill="x")

        self.state_label = ctk.CTkLabel(
            self.scroll,
            text=tr("Loading content..."),
            font=ctk.CTkFont(size=16),
            text_color=("gray50", "gray55"),
        )
        self.state_label.pack(pady=60)

        self._build_continue_watching()

        APIHolder.on_plugins_loaded(self._on_plugins_ready)
        if APIHolder.apis:
            self._on_plugins_ready()

    def _on_plugins_ready(self):
        if self._refresh_scheduled_id is not None:
            self.after_cancel(self._refresh_scheduled_id)
        self._refresh_scheduled_id = self.after(1500, self._do_first_refresh)

    def _do_first_refresh(self):
        self._refresh_scheduled_id = None
        self._update_provider_list()
        if not self.provider_var.get():
            return
        self.refresh()

    @staticmethod
    def _has_real_url(provider) -> bool:
        url = getattr(provider, "main_url", "") or ""
        return bool(url) and "example.com" not in url

    @staticmethod
    def _provider_priority(provider) -> int:
        mp = getattr(provider, "main_page", [])
        has_api = any(
            "/page/" in getattr(d, "data", "") or "/secure/" in getattr(d, "data", "")
            for d in mp
        )
        return 0 if has_api else 1

    def _update_provider_list(self):
        providers = [p for p in APIHolder.apis if p.has_main_page and self._has_real_url(p)]
        ranked = sorted(providers, key=self._provider_priority)
        names = [p.name for p in ranked]
        if not names:
            self.provider_menu.configure(values=[tr("No providers")])
            self.provider_var.set("")
            return
        self.provider_menu.configure(values=names)
        current = self.provider_var.get()
        if current not in names:
            self.provider_var.set(names[0])

    def refresh(self, force=False):
        if self._loading:
            return

        self._build_continue_watching()

        selected = self.provider_var.get()
        if not selected:
            self.state_label.configure(
                text=tr("No providers loaded.\nGo to Settings → Extensions to add plugins.")
            )
            return

        provider = None
        for p in APIHolder.apis:
            if p.name == selected:
                provider = p
                break
        if not provider:
            return

        if force:
            self._update_provider_list()

        self._clear_rows()
        self.state_label.configure(text=f"{selected} — {tr('Loading content...')}")
        self.state_label.pack(pady=60)

        print(f"[HomePage] Loading: {provider.name} ({len(provider.main_page)} kategori)")

        self._loading = True
        self._pending_requests = 0
        self.refresh_btn.configure(state="disabled")
        self._load_provider(provider, page=1)

    def _load_provider(self, provider, page: int):
        pages_to_load = provider.main_page[:8]
        self._pending_requests += len(pages_to_load)
        for pg_data in pages_to_load:
            request = MainPageRequest(
                name=pg_data.name,
                data=pg_data.data,
                horizontal_images=pg_data.horizontal_images,
            )
            self.app.run_async(
                provider.get_main_page(page, request),
                callback=lambda resp, prov=provider, req=request: self._on_home_response(resp, prov, req),
                error_callback=lambda e, prov=provider, req=request: self._on_error(e, prov, req),
            )

    def _on_home_response(self, response, provider, request=None):
        req_name = request.name if request else "?"
        self._pending_requests = max(0, self._pending_requests - 1)
        if response is None:
            self._check_all_done()
            return
        total_items = sum(len(item.list) for item in response.items)
        print(f"[HomePage] {provider.name}/{req_name}: "
              f"{len(response.items)} grup, {total_items} oge, hasNext={response.has_next}")
        self.state_label.pack_forget()
        items_to_add = [item for item in response.items if item.list]
        if items_to_add:
            self._add_rows_batched(items_to_add, 0)
        self._check_all_done()

    def _add_rows_batched(self, items, idx):
        if idx >= len(items):
            return
        row = HorizontalScrollRow(
            self.scroll,
            home_page_list=items[idx],
            on_card_click=self._on_card_click,
        )
        row.pack(fill="x", pady=2)
        if idx + 1 < len(items):
            self.after(30, lambda: self._add_rows_batched(items, idx + 1))

    def _on_error(self, error, provider, request=None):
        req_name = request.name if request else "?"
        self._pending_requests = max(0, self._pending_requests - 1)
        print(f"[HomePage] HATA {provider.name}/{req_name}: {error}")
        self._check_all_done()

    def _check_all_done(self):
        if self._pending_requests > 0:
            return
        self._loading = False
        self.refresh_btn.configure(state="normal")
        has_rows = any(isinstance(c, HorizontalScrollRow)
                       for c in self.scroll.winfo_children())
        if not has_rows:
            self.state_label.configure(
                text=tr("No content available from this provider.")
            )
            self.state_label.pack(pady=60)

    def _clear_rows(self):
        for widget in self.scroll.winfo_children():
            if isinstance(widget, HorizontalScrollRow):
                widget.destroy()

    # ------------------------------------------------------------------
    # Continue Watching
    # ------------------------------------------------------------------

    def _build_continue_watching(self):
        for w in self._continue_frame.winfo_children():
            w.destroy()

        entries = Database.get_continue_watching(limit=15)
        if not entries:
            return

        ctk.CTkLabel(
            self._continue_frame,
            text=f"▶ {tr('Continue Watching')}",
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=16, pady=(10, 2))

        scroll = ctk.CTkScrollableFrame(
            self._continue_frame,
            orientation="horizontal",
            height=130,
            fg_color="transparent",
            scrollbar_button_color=("#888", "#555"),
        )
        scroll.pack(fill="x", padx=8, pady=(0, 8))

        for entry in entries:
            self._make_continue_card(scroll, entry)

    _cw_image_refs: List = []

    def _make_continue_card(self, parent, entry):
        _THUMB_W, _THUMB_H = 60, 90
        _CARD_W, _CARD_H = 280, 110
        _TEXT_X = _THUMB_W + 14

        card = ctk.CTkFrame(parent, width=_CARD_W, height=_CARD_H,
                            fg_color=("gray82", "gray20"), corner_radius=10)
        card.pack(side="left", padx=5, pady=4)
        card.pack_propagate(False)

        thumb_label = ctk.CTkLabel(card, text="", width=_THUMB_W, height=_THUMB_H,
                                   fg_color=("gray70", "gray28"), corner_radius=6)
        thumb_label.place(x=6, y=10)

        if entry.poster_url:
            self._load_cw_thumbnail(thumb_label, entry.poster_url, _THUMB_W, _THUMB_H)

        ctk.CTkLabel(
            card, text=entry.name[:24],
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
        ).place(x=_TEXT_X, y=8)

        ep_text = entry.episode_name or ""
        if ep_text:
            ctk.CTkLabel(
                card, text=ep_text[:26],
                font=ctk.CTkFont(size=10),
                text_color=("gray40", "gray60"),
                anchor="w",
            ).place(x=_TEXT_X, y=30)

        progress = min(entry.position / entry.duration, 1.0) if entry.duration > 0 else 0
        remaining = max(0, entry.duration - entry.position)
        min_left = int(remaining / 60)

        bar = ctk.CTkProgressBar(card, width=_CARD_W - _TEXT_X - 10, height=6)
        bar.set(progress)
        bar.place(x=_TEXT_X, y=56)

        ctk.CTkLabel(
            card, text=f"{min_left} dk kaldı",
            font=ctk.CTkFont(size=9),
            text_color=("gray50", "gray55"),
        ).place(x=_TEXT_X, y=66)

        play_btn = ctk.CTkButton(
            card, text="▶  Devam Et", width=90, height=26,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("#1e88e5", "#1565c0"),
            hover_color=("#1565c0", "#0d47a1"),
            command=lambda e=entry: self._resume_entry(e),
        )
        play_btn.place(x=_TEXT_X, y=82)

        card.bind("<Button-1>", lambda ev, e=entry: self._resume_entry(e))

    def _load_cw_thumbnail(self, label, url, w, h):
        from ui.app import CloudStreamApp

        def _fetch():
            try:
                from ui.components.media_card import _cache_get, _cache_put
                from PIL import Image
                import io, httpx
                img = _cache_get(url)
                if img is None:
                    resp = httpx.get(url, timeout=8, follow_redirects=True)
                    resp.raise_for_status()
                    img = Image.open(io.BytesIO(resp.content)).convert("RGB")
                    _cache_put(url, img)
                thumb = img.resize((w, h), Image.LANCZOS)
                ctk_img = ctk.CTkImage(light_image=thumb, dark_image=thumb, size=(w, h))
                self._cw_image_refs.append(ctk_img)

                def _apply():
                    try:
                        if label.winfo_exists():
                            label.configure(image=ctk_img, text="")
                    except Exception:
                        pass

                label.after(0, _apply)
            except Exception:
                pass

        CloudStreamApp.get_image_pool().submit(_fetch)

    def _resume_entry(self, entry):
        if not entry.episode_data:
            return
        api = APIHolder.get_api_by_name(entry.api_name)
        if api is None:
            self.app.set_status(f"{entry.api_name} sağlayıcısı bulunamadı.")
            return

        self.app.set_status(f"Devam ediliyor: {entry.name}...")

        links: List[ExtractorLink] = []
        subs: List[SubtitleFile] = []

        async def _load():
            import asyncio
            from core.models import (
                TvSeriesLoadResponse, AnimeLoadResponse, Episode as EpModel
            )

            all_episodes: List = []

            async def _fetch_links():
                try:
                    await api.load_links(
                        entry.episode_data, False,
                        links.append, subs.append,
                    )
                except Exception as exc:
                    print(f"[Home] resume load_links error: {exc}")

            async def _fetch_episodes():
                try:
                    resp = await api.load(entry.url)
                    if isinstance(resp, TvSeriesLoadResponse):
                        all_episodes.extend(resp.episodes)
                    elif isinstance(resp, AnimeLoadResponse):
                        for eps in resp.episodes.values():
                            all_episodes.extend(eps)
                except Exception as exc:
                    print(f"[Home] resume load_episodes error: {exc}")

            await asyncio.gather(_fetch_links(), _fetch_episodes())
            return links, subs, all_episodes

        def _done(result):
            lks, ss, all_eps = result
            if not lks:
                self.app.set_status("Oynatılabilir bağlantı bulunamadı.")
                return
            from core.models import Episode
            ep = Episode(
                data=entry.episode_data,
                name=entry.episode_name,
                episode=entry.episode,
                season=entry.season,
            )
            self.app.navigate_to_player(
                links=lks, subtitles=ss, title=entry.name, episode=ep,
                content_url=entry.url, api_name=entry.api_name,
                poster_url=entry.poster_url or "",
                resume_position=entry.position,
                all_episodes=all_eps,
            )

        def _err(e):
            self.app.set_status(f"Hata: {e}")

        self.app.run_async(_load(), callback=_done, error_callback=_err)

    def _on_card_click(self, result: SearchResponse):
        self.app.navigate_to_result(result)

    def navigate(self, **kwargs):
        self._build_continue_watching()

    def _on_provider_changed(self, value: str):
        self.refresh(force=True)
