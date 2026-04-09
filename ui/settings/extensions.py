"""
ExtensionsPage — manage plugin repositories and installed/available plugins.
"""
from __future__ import annotations
import asyncio
import io
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, List, Optional, Tuple

import customtkinter as ctk
from PIL import Image

from plugins.repository_manager import RepositoryManager, SitePlugin
from plugins.plugin_manager import PluginManager
from core.i18n import tr

if TYPE_CHECKING:
    from ui.app import CloudStreamApp


class ExtensionsPage(ctk.CTkFrame):
    def __init__(self, parent, app: "CloudStreamApp", **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.app = app
        self._available: List[Tuple[str, SitePlugin]] = []
        self._filtered: List[Tuple[str, SitePlugin]] = []
        self._build()

    def _build(self):
        # ---- Repositories section ----
        self._section_label(tr("Repositories"))

        repo_frame = ctk.CTkFrame(self, fg_color=("gray85", "gray20"), corner_radius=8)
        repo_frame.pack(fill="x", padx=12, pady=4)

        # Add repo bar
        add_bar = ctk.CTkFrame(repo_frame, fg_color="transparent")
        add_bar.pack(fill="x", padx=8, pady=6)

        self.repo_entry = ctk.CTkEntry(
            add_bar,
            placeholder_text=tr("Repository URL (https://...)"),
            font=ctk.CTkFont(size=12),
            height=32,
        )
        self.repo_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        ctk.CTkButton(
            add_bar, text=tr("Add Repo"), width=100, height=32,
            command=self._add_repo,
        ).pack(side="left")

        # Repo list
        self.repo_list_frame = ctk.CTkFrame(repo_frame, fg_color="transparent")
        self.repo_list_frame.pack(fill="x", padx=8, pady=(0, 6))
        self._refresh_repo_list()

        # ---- Plugins section ----
        self._section_label(tr("Plugins"))

        # Search + filters
        filter_bar = ctk.CTkFrame(self, fg_color="transparent")
        filter_bar.pack(fill="x", padx=12, pady=4)

        self.plugin_search = ctk.CTkEntry(
            filter_bar, placeholder_text=tr("Search plugins..."), height=32, width=220,
        )
        self.plugin_search.pack(side="left", padx=(0, 6))
        self.plugin_search.bind("<KeyRelease>", lambda e: self._apply_filter())

        self.lang_filter = ctk.CTkOptionMenu(
            filter_bar, values=["Hepsi", "tr", "en", "de", "fr", "es", "ja", "ko"],
            width=90, height=32,
            command=lambda _: self._apply_filter(),
        )
        self.lang_filter.pack(side="left", padx=4)

        self.type_filter = ctk.CTkOptionMenu(
            filter_bar,
            values=[tr("All Types"), "Movie", "TvSeries", "Anime", "AsianDrama"],
            width=120, height=32,
            command=lambda _: self._apply_filter(),
        )
        self.type_filter.pack(side="left", padx=4)

        ctk.CTkButton(
            filter_bar, text=tr("↻ Fetch"), width=80, height=32,
            command=self._fetch_all_plugins,
        ).pack(side="left", padx=4)

        self.install_all_btn = ctk.CTkButton(
            filter_bar, text="⬇ Tümünü Yükle", width=120, height=32,
            fg_color="#1a73e8",
            command=self._install_all_plugins,
        )
        self.install_all_btn.pack(side="left", padx=4)
        self.install_all_btn.pack_forget()  # başlangıçta gizli

        self.plugin_count_label = ctk.CTkLabel(
            filter_bar, text="", font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray55"),
        )
        self.plugin_count_label.pack(side="right", padx=4)

        # Plugin list
        self.plugin_scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent", height=400
        )
        self.plugin_scroll.pack(fill="both", expand=True, padx=12, pady=4)

        self.plugin_state_label = ctk.CTkLabel(
            self.plugin_scroll,
            text=tr('Click "↻ Fetch" to load available plugins from repositories.'),
            font=ctk.CTkFont(size=13),
            text_color=("gray50", "gray55"),
        )
        self.plugin_state_label.pack(pady=40)

        # Load currently installed plugins
        self._refresh_installed()

    # ------------------------------------------------------------------
    # Repositories
    # ------------------------------------------------------------------

    def _refresh_repo_list(self):
        for w in self.repo_list_frame.winfo_children():
            w.destroy()

        repos = RepositoryManager.get_repositories()
        if not repos:
            ctk.CTkLabel(
                self.repo_list_frame,
                text=tr("No repositories added yet."),
                font=ctk.CTkFont(size=11),
                text_color=("gray50", "gray55"),
            ).pack(anchor="w", padx=4, pady=4)
            return

        for url in repos:
            row = ctk.CTkFrame(self.repo_list_frame, fg_color="transparent", height=32)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)

            short = url[:60] + "..." if len(url) > 60 else url
            ctk.CTkLabel(row, text=short, font=ctk.CTkFont(size=11), anchor="w").pack(
                side="left", padx=4
            )
            ctk.CTkButton(
                row, text="✕", width=28, height=24,
                fg_color=("gray65", "gray30"),
                command=lambda u=url: self._remove_repo(u),
            ).pack(side="right", padx=4)

    def _add_repo(self):
        url = self.repo_entry.get().strip()
        if not url:
            return
        if RepositoryManager.add_repository(url):
            self.repo_entry.delete(0, "end")
            self._refresh_repo_list()
            self.app.set_status(f"{tr('Repository added')}: {url[:50]}")
        else:
            self.app.set_status(tr("Repository already exists."))

    def _remove_repo(self, url: str):
        RepositoryManager.remove_repository(url)
        self._refresh_repo_list()
        self.app.set_status(tr("Repository removed."))

    # ------------------------------------------------------------------
    # Plugins
    # ------------------------------------------------------------------

    def _fetch_all_plugins(self):
        # Mevcut tüm widget'ları temizle ve state label'ı yeniden oluştur
        for w in self.plugin_scroll.winfo_children():
            w.destroy()

        self.plugin_state_label = ctk.CTkLabel(
            self.plugin_scroll,
            text=tr("Fetching plugins from repositories..."),
            font=ctk.CTkFont(size=13),
            text_color=("gray50", "gray55"),
        )
        self.plugin_state_label.pack(pady=40)

        def _run():
            result = asyncio.run(RepositoryManager.get_all_plugins())
            self.after(0, lambda: self._on_plugins_fetched(result))

        threading.Thread(target=_run, daemon=True).start()

    def _on_plugins_fetched(self, plugins: List[Tuple[str, SitePlugin]]):
        self._available = plugins
        # _apply_filter -> _render_plugin_list tüm widget'ları yeniden oluşturur
        self._apply_filter()

    def _apply_filter(self):
        query = self.plugin_search.get().strip().lower()
        lang = self.lang_filter.get()
        tv_type = self.type_filter.get()

        filtered = self._available
        if query:
            filtered = [
                (u, p) for u, p in filtered
                if query in p.name.lower() or query in p.description.lower()
            ]
        if lang not in ("Hepsi", "All"):
            filtered = [(u, p) for u, p in filtered if p.language == lang]
        if tv_type not in (tr("All Types"), "All Types"):
            filtered = [(u, p) for u, p in filtered if tv_type in (p.tv_types or [])]

        self._filtered = filtered
        not_installed = [(u, p) for u, p in filtered
                         if not RepositoryManager.is_installed(p.internal_name)]
        self.plugin_count_label.configure(text=f"{len(filtered)} eklenti")
        if not_installed:
            self.install_all_btn.pack(side="left", padx=4)
        else:
            self.install_all_btn.pack_forget()
        self._render_plugin_list()

    def _render_plugin_list(self):
        for w in self.plugin_scroll.winfo_children():
            w.destroy()

        if not self._filtered:
            if not self._available:
                self._refresh_installed()
            else:
                ctk.CTkLabel(
                    self.plugin_scroll, text=tr("No plugins match the filter."),
                    font=ctk.CTkFont(size=13), text_color=("gray50", "gray55"),
                ).pack(pady=40)
            return

        for repo_url, plugin in self._filtered:
            PluginRow(
                self.plugin_scroll,
                plugin=plugin,
                on_install=self._install_plugin,
                on_update=self._update_plugin,
                on_uninstall=self._uninstall_plugin,
            ).pack(fill="x", padx=4, pady=2)

    def _refresh_installed(self):
        for w in self.plugin_scroll.winfo_children():
            w.destroy()

        installed = PluginManager.get_plugin_data()
        if not installed:
            ctk.CTkLabel(
                self.plugin_scroll,
                text=tr('No plugins installed.\nAdd a repository above and click "↻ Fetch".'),
                font=ctk.CTkFont(size=13),
                text_color=("gray50", "gray55"),
            ).pack(pady=40)
            return

        ctk.CTkLabel(
            self.plugin_scroll, text=tr("Installed Plugins"),
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=4, pady=4)

        for fp, pdata in installed.items():
            row = ctk.CTkFrame(
                self.plugin_scroll, fg_color=("gray85", "gray22"), corner_radius=6, height=44,
            )
            row.pack(fill="x", padx=4, pady=2)
            row.pack_propagate(False)

            ctk.CTkLabel(
                row, text=pdata.internal_name, font=ctk.CTkFont(size=13), anchor="w",
            ).pack(side="left", padx=10)
            ctk.CTkLabel(
                row, text=f"v{pdata.version}", font=ctk.CTkFont(size=11),
                text_color=("gray50", "gray60"),
            ).pack(side="left", padx=4)

            ctk.CTkButton(
                row, text=tr("Uninstall"), width=90, height=28,
                fg_color=("gray65", "gray30"),
                command=lambda f=fp: self._uninstall_by_path(f),
            ).pack(side="right", padx=8, pady=6)

    def _install_plugin(self, plugin: SitePlugin):
        self.app.set_status(f"Yükleniyor: {plugin.name}...")

        def _run():
            result = RepositoryManager.download_plugin_sync(plugin)
            self.after(0, lambda: self.app.set_status(
                f"{'Yüklendi ✓' if result else 'Başarısız ✗'}: {plugin.name}"
            ))
            self.after(0, self._apply_filter)

        threading.Thread(target=_run, daemon=True).start()

    def _update_plugin(self, plugin: SitePlugin):
        self.app.set_status(f"Güncelleniyor: {plugin.name}...")

        def _run():
            result = RepositoryManager.update_plugin_sync(plugin)
            self.after(0, lambda: self.app.set_status(
                f"{'Güncellendi ✓' if result else 'Güncelleme başarısız ✗'}: {plugin.name}"
            ))
            self.after(0, self._apply_filter)

        threading.Thread(target=_run, daemon=True).start()

    def _install_all_plugins(self):
        not_installed = [(u, p) for u, p in self._filtered
                         if not RepositoryManager.is_installed(p.internal_name)]
        if not not_installed:
            return

        total = len(not_installed)
        self.app.set_status(f"0/{total} eklenti yükleniyor...")
        self.install_all_btn.configure(state="disabled")

        def _run_batch():
            done = 0
            failed = 0
            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = {
                    pool.submit(RepositoryManager.download_plugin_sync, plugin): plugin
                    for _, plugin in not_installed
                }
                from concurrent.futures import as_completed
                for future in as_completed(futures):
                    plugin = futures[future]
                    try:
                        success = future.result()
                        if not success:
                            failed += 1
                    except Exception as e:
                        print(f"[Extensions] Install error [{plugin.name}]: {e}")
                        failed += 1
                    done += 1
                    n, f = done, failed
                    self.after(0, lambda n=n, f=f: self.app.set_status(
                        f"{n}/{total} eklenti yüklendi" + (f" ({f} başarısız)" if f else "")
                    ))

            self.after(0, self._apply_filter)
            self.after(0, lambda: self.install_all_btn.configure(state="normal"))
            from core.api_holder import APIHolder
            self.after(0, lambda: APIHolder.notify_plugins_loaded())

        threading.Thread(target=_run_batch, daemon=True).start()

    def _uninstall_plugin(self, plugin: SitePlugin):
        # Registry'den dosya yolunu bul (uzantı .cs3 olabilir)
        for fp, pd in PluginManager.get_plugin_data().items():
            if pd.internal_name == plugin.internal_name:
                self._uninstall_by_path(fp)
                return

    def _uninstall_by_path(self, file_path: str):
        PluginManager.delete_plugin(file_path)
        self.app.set_status(tr("Plugin uninstalled."))
        self._apply_filter()

    def _section_label(self, text: str):
        ctk.CTkLabel(
            self, text=text,
            font=ctk.CTkFont(size=15, weight="bold"),
            anchor="w",
        ).pack(anchor="w", padx=12, pady=(12, 0))
        ctk.CTkFrame(self, height=1, fg_color=("gray70", "gray35")).pack(
            fill="x", padx=12, pady=(2, 0)
        )


class PluginRow(ctk.CTkFrame):
    """Tek bir eklenti satırı."""

    # Renk paleti — plugin adının ilk harfine göre renk seç
    _COLORS = [
        "#1a73e8", "#e53935", "#43a047", "#fb8c00",
        "#8e24aa", "#00897b", "#3949ab", "#6d4c41",
    ]

    def __init__(self, parent, plugin: SitePlugin, on_install, on_update, on_uninstall, **kwargs):
        super().__init__(
            parent, fg_color=("gray87", "gray21"), corner_radius=8, height=60, **kwargs
        )
        self.pack_propagate(False)
        self.plugin = plugin
        self.on_install = on_install
        self.on_update = on_update
        self.on_uninstall = on_uninstall
        self._icon_label: Optional[ctk.CTkLabel] = None
        self._build()
        # İkon yüklemeyi arka planda başlat
        if plugin.icon_url:
            threading.Thread(target=self._load_icon, args=(plugin.icon_url,), daemon=True).start()

    # ------------------------------------------------------------------ #
    def _accent(self) -> str:
        idx = sum(ord(c) for c in self.plugin.name) % len(self._COLORS)
        return self._COLORS[idx]

    def _build(self):
        # Sol: ikon çerçevesi
        self._icon_frame = ctk.CTkFrame(
            self, width=44, height=44,
            fg_color=self._accent(), corner_radius=10,
        )
        self._icon_frame.pack(side="left", padx=(10, 6), pady=8)
        self._icon_frame.pack_propagate(False)

        self._icon_label = ctk.CTkLabel(
            self._icon_frame,
            text=self.plugin.name[:2].upper(),
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="white",
        )
        self._icon_label.place(relx=0.5, rely=0.5, anchor="center")

        # Orta: bilgi
        info = ctk.CTkFrame(self, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True, padx=(0, 4))

        top = ctk.CTkFrame(info, fg_color="transparent")
        top.pack(fill="x", pady=(6, 0))

        ctk.CTkLabel(
            top, text=self.plugin.name,
            font=ctk.CTkFont(size=13, weight="bold"), anchor="w",
        ).pack(side="left")

        ctk.CTkLabel(
            top, text=f"v{self.plugin.version}",
            font=ctk.CTkFont(size=10), text_color=("gray50", "gray60"),
        ).pack(side="left", padx=(4, 2))

        lang_label = ctk.CTkLabel(
            top, text=f"  {self.plugin.language}  ",
            font=ctk.CTkFont(size=9),
            fg_color=("gray75", "gray35"), corner_radius=4,
            text_color=("gray20", "gray80"),
        )
        lang_label.pack(side="left", padx=2)

        if self.plugin.author:
            ctk.CTkLabel(
                top, text=f"@ {self.plugin.author}",
                font=ctk.CTkFont(size=9), text_color=("gray55", "gray55"),
            ).pack(side="left", padx=(4, 0))

        if self.plugin.description:
            ctk.CTkLabel(
                info, text=self.plugin.description[:80],
                font=ctk.CTkFont(size=10),
                text_color=("gray50", "gray55"), anchor="w",
            ).pack(anchor="w", pady=(0, 4))

        # Sağ: aksiyon butonu
        is_installed = RepositoryManager.is_installed(self.plugin.internal_name)
        installed_ver = RepositoryManager.get_installed_version(self.plugin.internal_name)
        has_update = is_installed and installed_ver is not None and self.plugin.version > installed_ver

        if has_update:
            ctk.CTkButton(
                self, text=tr("↑ Update"), width=90, height=30,
                fg_color="#f57c00",
                command=lambda: self.on_update(self.plugin),
            ).pack(side="right", padx=(4, 10), pady=8)
        elif is_installed:
            ctk.CTkButton(
                self, text=tr("Uninstall"), width=90, height=30,
                fg_color=("gray62", "gray32"),
                command=lambda: self.on_uninstall(self.plugin),
            ).pack(side="right", padx=(4, 10), pady=8)
        else:
            ctk.CTkButton(
                self, text=tr("Install"), width=90, height=30,
                fg_color="#1a73e8",
                command=lambda: self.on_install(self.plugin),
            ).pack(side="right", padx=(4, 10), pady=8)

    def _load_icon(self, url: str):
        """Arka planda ikon URL'sinden görüntü indir ve göster."""
        try:
            import httpx
            with httpx.Client(follow_redirects=True, timeout=10) as client:
                resp = client.get(url)
                resp.raise_for_status()
                img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
                img = img.resize((40, 40), Image.LANCZOS)
                ctk_img = ctk.CTkImage(img, size=(40, 40))
                # GUI güncellemesi ana thread'de yapılmalı
                if self.winfo_exists() and self._icon_label and self._icon_label.winfo_exists():
                    self.after(0, lambda: self._apply_icon(ctk_img))
        except Exception:
            pass  # Hata durumunda placeholder kalır

    def _apply_icon(self, ctk_img: ctk.CTkImage):
        if not self.winfo_exists():
            return
        # Arka plan rengini nötr yap, label'ı resimle güncelle
        self._icon_frame.configure(fg_color=("gray80", "gray28"))
        if self._icon_label and self._icon_label.winfo_exists():
            self._icon_label.configure(image=ctk_img, text="")
