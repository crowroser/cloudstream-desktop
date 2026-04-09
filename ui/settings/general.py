"""
SettingsPage — tabbed settings container with sub-pages.
"""
from __future__ import annotations
from typing import TYPE_CHECKING
import os
from pathlib import Path

import customtkinter as ctk

from data.preferences import Preferences
from core.i18n import tr

if TYPE_CHECKING:
    from ui.app import CloudStreamApp


class SettingsPage(ctk.CTkFrame):
    def __init__(self, parent, app: "CloudStreamApp", **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.app = app
        self._build()

    def _build(self):
        header = ctk.CTkFrame(self, height=52, fg_color=("gray88", "gray14"), corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header, text=tr("Settings"),
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(side="left", padx=16, pady=12)

        tabs = ctk.CTkTabview(self)
        tabs.pack(fill="both", expand=True, padx=8, pady=8)

        tabs.add(tr("General"))
        tabs.add(tr("Player"))
        tabs.add(tr("Downloads"))
        tabs.add(tr("Providers"))
        tabs.add(tr("Sync"))
        tabs.add(tr("Extensions"))
        tabs.add(tr("About"))

        self._build_general(tabs.tab(tr("General")))
        self._build_player(tabs.tab(tr("Player")))
        self._build_downloads(tabs.tab(tr("Downloads")))
        self._build_providers(tabs.tab(tr("Providers")))
        self._build_sync(tabs.tab(tr("Sync")))
        self._build_extensions_link(tabs.tab(tr("Extensions")))
        self._build_about(tabs.tab(tr("About")))

    # ------------------------------------------------------------------
    # General
    # ------------------------------------------------------------------

    def _build_general(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        self._section(scroll, tr("Appearance"))

        self._row(scroll, tr("Theme"),
                  ctk.CTkOptionMenu(scroll, values=["dark", "light", "system"], width=140,
                                    command=lambda v: self._set_and_apply("theme", v,
                                                                          lambda: ctk.set_appearance_mode(v))))
        self._row(scroll, tr("Accent Color"),
                  ctk.CTkOptionMenu(scroll, values=["blue", "green", "dark-blue"], width=140,
                                    command=lambda v: self._pref_set("accent_color", v)))

        self._section(scroll, tr("Language"))
        lang_menu = ctk.CTkOptionMenu(
            scroll,
            values=["tr", "en", "de", "fr", "es", "ja", "ko"],
            width=140,
            command=lambda v: self._pref_set("language", v),
        )
        lang_menu.set(Preferences.get_str("language", "tr"))
        self._row(scroll, tr("Interface Language"), lang_menu)

    # ------------------------------------------------------------------
    # Player
    # ------------------------------------------------------------------

    def _build_player(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        self._section(scroll, tr("Playback"))
        self._bool_row(scroll, tr("Remember playback position"), "player_remember_position")
        self._bool_row(scroll, tr("Auto-play next episode"), "player_auto_next")
        self._bool_row(scroll, tr("Skip intro (AniSkip)"), "player_skip_intro")

        self._section(scroll, tr("Subtitles"))
        self._bool_row(scroll, tr("Enable subtitles by default"), "player_subtitles_enabled")
        self._row(scroll, tr("Default subtitle language"),
                  ctk.CTkEntry(scroll, width=80,
                               textvariable=ctk.StringVar(value=Preferences.get_str("player_subtitle_lang"))))
        self._row(scroll, tr("Subtitle font size"),
                  ctk.CTkSlider(scroll, from_=12, to=48, width=200,
                                command=lambda v: self._pref_set("player_subtitle_size", int(v))))

        self._section(scroll, tr("Volume"))
        vol_slider = ctk.CTkSlider(scroll, from_=0, to=100, width=200,
                                   command=lambda v: self._pref_set("player_volume", int(v)))
        vol_slider.set(Preferences.get_int("player_volume", 100))
        self._row(scroll, tr("Default volume"), vol_slider)

    # ------------------------------------------------------------------
    # Downloads
    # ------------------------------------------------------------------

    def _build_downloads(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        self._section(scroll, tr("Download Location"))
        path_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        path_frame.pack(fill="x", padx=12, pady=4)

        self.dl_path_var = ctk.StringVar(value=Preferences.get_str("download_path"))
        entry = ctk.CTkEntry(path_frame, textvariable=self.dl_path_var, width=360)
        entry.pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            path_frame, text=tr("Browse"), width=80,
            command=self._browse_download_path,
        ).pack(side="left")

        self._section(scroll, tr("Parallel Downloads"))
        self._row(scroll, tr("Max simultaneous downloads"),
                  ctk.CTkOptionMenu(scroll, values=["1", "2", "3", "4", "5"], width=80,
                                    command=lambda v: self._pref_set("max_parallel_downloads", int(v))))

    def _browse_download_path(self):
        from tkinter import filedialog
        path = filedialog.askdirectory(initialdir=self.dl_path_var.get())
        if path:
            self.dl_path_var.set(path)
            Preferences.set("download_path", path)

    # ------------------------------------------------------------------
    # Providers
    # ------------------------------------------------------------------

    def _build_providers(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        self._section(scroll, tr("Content Filters"))
        self._bool_row(scroll, tr("Show adult (18+) content"), "show_adult_content")

        self._section(scroll, tr("Loaded Providers"))
        from core.api_holder import APIHolder
        for api in APIHolder.apis:
            row = ctk.CTkFrame(scroll, fg_color=("gray82", "gray22"), corner_radius=6, height=40)
            row.pack(fill="x", padx=12, pady=2)
            row.pack_propagate(False)
            ctk.CTkLabel(row, text=api.name, font=ctk.CTkFont(size=13), anchor="w").pack(
                side="left", padx=10
            )
            ctk.CTkLabel(row, text=api.lang, font=ctk.CTkFont(size=11),
                         text_color=("gray50", "gray60")).pack(side="left", padx=4)
            types = ", ".join(t.value for t in getattr(api, "supported_types", [])[:3])
            if types:
                ctk.CTkLabel(row, text=types, font=ctk.CTkFont(size=11),
                             text_color=("gray50", "gray60")).pack(side="right", padx=10)

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------

    def _build_sync(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        for service, key in [("AniList", "anilist_token"), ("MyAnimeList", "mal_token"),
                              ("Simkl", "simkl_token")]:
            self._section(scroll, service)
            token = Preferences.get_str(key, "")
            status = tr("Connected ✓") if token else tr("Not connected")
            ctk.CTkLabel(scroll, text=status, font=ctk.CTkFont(size=12),
                         text_color="#4caf50" if token else ("gray50", "gray55")).pack(
                anchor="w", padx=16, pady=2
            )
            btn_text = tr("Disconnect") if token else f"{service} {tr('Connect')}"
            ctk.CTkButton(
                scroll,
                text=btn_text,
                width=160, height=30,
                command=lambda s=service, k=key: self._sync_action(s, k),
            ).pack(anchor="w", padx=16, pady=4)

    def _sync_action(self, service: str, key: str):
        token = Preferences.get_str(key, "")
        if token:
            Preferences.set(key, None)
        else:
            dialog = TokenDialog(self, service)
            self.wait_window(dialog)
            if dialog.result:
                Preferences.set(key, dialog.result)

    # ------------------------------------------------------------------
    # Extensions link
    # ------------------------------------------------------------------

    def _build_extensions_link(self, parent):
        from ui.settings.extensions import ExtensionsPage
        ExtensionsPage(parent, app=self.app).pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    # About
    # ------------------------------------------------------------------

    def _build_about(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(expand=True)

        ctk.CTkLabel(frame, text="☁  CloudStream Desktop",
                     font=ctk.CTkFont(size=26, weight="bold"),
                     text_color=("#1a73e8", "#4fc3f7")).pack(pady=(40, 8))
        ctk.CTkLabel(frame, text=tr("Python-powered media center with plugin support"),
                     font=ctk.CTkFont(size=14),
                     text_color=("gray40", "gray60")).pack()
        ctk.CTkLabel(frame, text="Sürüm 1.0.0",
                     font=ctk.CTkFont(size=12)).pack(pady=4)
        ctk.CTkLabel(frame, text=tr("Inspired by CloudStream (Android) by recloudstream"),
                     font=ctk.CTkFont(size=11),
                     text_color=("gray50", "gray55")).pack(pady=2)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _section(self, parent, title: str):
        ctk.CTkLabel(parent, text=title,
                     font=ctk.CTkFont(size=14, weight="bold"),
                     anchor="w").pack(anchor="w", padx=12, pady=(12, 2))
        ctk.CTkFrame(parent, height=1, fg_color=("gray70", "gray35")).pack(
            fill="x", padx=12, pady=(0, 4)
        )

    def _row(self, parent, label: str, widget):
        row = ctk.CTkFrame(parent, fg_color="transparent", height=36)
        row.pack(fill="x", padx=12, pady=2)
        row.pack_propagate(False)
        ctk.CTkLabel(row, text=label, font=ctk.CTkFont(size=12), anchor="w").pack(
            side="left", expand=True, fill="x"
        )
        widget.pack(side="right")

    def _bool_row(self, parent, label: str, pref_key: str):
        row = ctk.CTkFrame(parent, fg_color="transparent", height=36)
        row.pack(fill="x", padx=12, pady=2)
        row.pack_propagate(False)
        ctk.CTkLabel(row, text=label, font=ctk.CTkFont(size=12), anchor="w").pack(
            side="left", expand=True, fill="x"
        )
        var = ctk.BooleanVar(value=Preferences.get_bool(pref_key))
        ctk.CTkSwitch(row, text="", variable=var,
                      command=lambda: Preferences.set(pref_key, var.get())).pack(side="right")

    def _pref_set(self, key: str, value):
        Preferences.set(key, value)

    def _set_and_apply(self, key: str, value, apply_fn=None):
        Preferences.set(key, value)
        if apply_fn:
            apply_fn()


class TokenDialog(ctk.CTkToplevel):
    def __init__(self, parent, service: str):
        super().__init__(parent)
        self.result = None
        self.title(f"{service} {tr('Connect')}")
        self.geometry("400x180")
        self.resizable(False, False)

        ctk.CTkLabel(self, text=f"{service} API token'ını girin:").pack(pady=(20, 4))
        self.entry = ctk.CTkEntry(self, width=320, show="•")
        self.entry.pack(pady=4)

        ctk.CTkButton(self, text=tr("Connect"), command=self._confirm).pack(pady=12)
        self.grab_set()

    def _confirm(self):
        self.result = self.entry.get().strip()
        self.destroy()
