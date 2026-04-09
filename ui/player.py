"""
PlayerPage — uygulama ici gomulu video oynatici (libmpv tabanli).
"""
from __future__ import annotations
import os
import sys
import tkinter as tk
from typing import List, Optional, TYPE_CHECKING

import customtkinter as ctk
from core.models import ExtractorLink, SubtitleFile, Episode

if TYPE_CHECKING:
    from ui.app import CloudStreamApp

_EP_PANEL_W = 300

mpv = None
_MPV_OK = False


def _ensure_mpv():
    """Lazy-import mpv, patching DLL search on Windows if needed."""
    global mpv, _MPV_OK
    if _MPV_OK:
        return True

    _app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dll_path = os.path.join(_app_root, "libmpv-2.dll")

    _orig_find = None
    if sys.platform == "win32" and os.path.isfile(dll_path):
        import ctypes.util
        _orig_find = ctypes.util.find_library

        def _patched(name):
            if "mpv" in name:
                return dll_path
            return _orig_find(name)

        ctypes.util.find_library = _patched

        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(_app_root)
            except OSError:
                pass
        os.environ["PATH"] = _app_root + os.pathsep + os.environ.get("PATH", "")

    try:
        if "mpv" in sys.modules:
            del sys.modules["mpv"]
        import importlib
        mpv = importlib.import_module("mpv")
        _MPV_OK = True
        print("[Player] mpv yuklendi basariyla")
    except (ImportError, OSError) as e:
        print(f"[Player] mpv yuklenemedi: {e}")
        _MPV_OK = False
    finally:
        if _orig_find is not None:
            import ctypes.util
            ctypes.util.find_library = _orig_find

    return _MPV_OK


_OVERLAY_BG = "#181818"
_OVERLAY_HIDE_MS = 3000


class PlayerPage(ctk.CTkFrame):
    def __init__(self, parent, app: "CloudStreamApp", **kwargs):
        super().__init__(parent, fg_color="black", **kwargs)
        self.app = app
        self._player = None
        self._links: List[ExtractorLink] = []
        self._subtitles: List[SubtitleFile] = []
        self._title_str = ""
        self._episode: Optional[Episode] = None
        self._current_link_idx = 0
        self._is_paused = False
        self._duration = 0.0
        self._position = 0.0
        self._seeking = False
        self._update_job = None
        self._fullscreen = False
        self._overlay_hide_job = None
        self._overlay_visible = False
        self._content_url = ""
        self._api_name = ""
        self._poster_url = ""
        self._resume_position = 0.0
        self._did_initial_seek = False
        self._save_job = None
        self._all_episodes: List[Episode] = []
        self._current_ep_index = -1
        self._ep_panel_visible = False
        self._ep_panel = None
        self._loading_episode = False
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Top bar (normal mode)
        self._top_bar = ctk.CTkFrame(self, height=40, fg_color=("gray15", "gray8"),
                                     corner_radius=0)
        self._top_bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        self._top_bar.grid_propagate(False)

        ctk.CTkButton(
            self._top_bar, text="Geri", width=70, height=30,
            fg_color="transparent", hover_color="gray25",
            text_color="gray70", font=ctk.CTkFont(size=12),
            command=self._go_back,
        ).pack(side="left", padx=8, pady=5)

        self._title_label = ctk.CTkLabel(
            self._top_bar, text="", font=ctk.CTkFont(size=13, weight="bold"),
            text_color="gray80",
        )
        self._title_label.pack(side="left", padx=8)

        # Video area
        self._video_frame = tk.Frame(self, bg="black")
        self._video_frame.grid(row=1, column=0, sticky="nsew")
        self._video_frame.bind("<Double-Button-1>", lambda e: self._toggle_fullscreen())
        self._video_frame.bind("<Motion>", self._on_mouse_move)
        self._video_frame.bind("<Button-1>", self._on_video_click)

        # Controls bar (normal mode)
        self._controls = ctk.CTkFrame(self, height=80, fg_color=("gray12", "gray8"),
                                      corner_radius=0)
        self._controls.grid(row=2, column=0, columnspan=2, sticky="ew")
        self._controls.grid_propagate(False)
        self._build_controls()

        # Fullscreen overlay (initially hidden, created on app root)
        self._overlay = None

    def _build_controls(self):
        seek_row = ctk.CTkFrame(self._controls, fg_color="transparent")
        seek_row.pack(fill="x", padx=12, pady=(8, 0))

        self._time_label = ctk.CTkLabel(
            seek_row, text="0:00 / 0:00",
            font=ctk.CTkFont(size=11), text_color="gray60", width=100,
        )
        self._time_label.pack(side="left")

        self._seek_bar = ctk.CTkSlider(
            seek_row, from_=0, to=1000, height=14,
            command=self._on_seek_drag,
            button_color=("#2196f3", "#2196f3"),
            progress_color=("#1565c0", "#1565c0"),
        )
        self._seek_bar.set(0)
        self._seek_bar.pack(side="left", fill="x", expand=True, padx=8)
        self._seek_bar.bind("<ButtonRelease-1>", self._on_seek_release)

        btn_row = ctk.CTkFrame(self._controls, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(4, 4))

        self._prev_btn = ctk.CTkButton(
            btn_row, text="⏮", width=36, height=32,
            font=ctk.CTkFont(size=14), fg_color="transparent",
            hover_color="gray25", text_color="gray50",
            command=self._play_prev_episode, state="disabled",
        )
        self._prev_btn.pack(side="left", padx=(0, 2))

        self._play_btn = ctk.CTkButton(
            btn_row, text="II", width=40, height=32,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="transparent", hover_color="gray25", text_color="white",
            command=self._toggle_pause,
        )
        self._play_btn.pack(side="left")

        self._next_btn = ctk.CTkButton(
            btn_row, text="⏭", width=36, height=32,
            font=ctk.CTkFont(size=14), fg_color="transparent",
            hover_color="gray25", text_color="gray50",
            command=self._play_next_episode, state="disabled",
        )
        self._next_btn.pack(side="left", padx=(2, 4))

        ctk.CTkButton(
            btn_row, text="-10s", width=50, height=32,
            fg_color="transparent", hover_color="gray25", text_color="gray70",
            font=ctk.CTkFont(size=11),
            command=lambda: self._seek_relative(-10),
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            btn_row, text="+10s", width=50, height=32,
            fg_color="transparent", hover_color="gray25", text_color="gray70",
            font=ctk.CTkFont(size=11),
            command=lambda: self._seek_relative(10),
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            btn_row, text="⏭ Intro Atla", width=90, height=32,
            fg_color=("#7b1fa2", "#6a1b9a"), hover_color=("#4a148c", "#4a148c"),
            text_color="white", font=ctk.CTkFont(size=11, weight="bold"),
            command=lambda: self._seek_relative(90),
        ).pack(side="left", padx=(6, 2))

        self._vol_slider = ctk.CTkSlider(
            btn_row, from_=0, to=100, width=80, height=14,
            command=self._on_volume,
        )
        self._vol_slider.set(100)
        self._vol_slider.pack(side="left", padx=(12, 4))

        self._quality_frame = ctk.CTkFrame(btn_row, fg_color="transparent")
        self._quality_frame.pack(side="left", padx=8)

        self._sub_frame = ctk.CTkFrame(btn_row, fg_color="transparent")
        self._sub_frame.pack(side="left", padx=4)

        self._ep_label = ctk.CTkLabel(
            btn_row, text="", font=ctk.CTkFont(size=11), text_color="gray60",
        )
        self._ep_label.pack(side="right", padx=8)

        ctk.CTkButton(
            btn_row, text="Tam Ekran", width=70, height=32,
            fg_color="transparent", hover_color="gray25", text_color="white",
            font=ctk.CTkFont(size=11),
            command=self._toggle_fullscreen,
        ).pack(side="right")

        self._ep_list_btn = ctk.CTkButton(
            btn_row, text="☰ Bölümler", width=90, height=32,
            fg_color=("#00897b", "#00695c"), hover_color=("#004d40", "#004d40"),
            text_color="white", font=ctk.CTkFont(size=11, weight="bold"),
            command=self._toggle_episode_panel, state="disabled",
        )
        self._ep_list_btn.pack(side="right", padx=(0, 6))

    # ------------------------------------------------------------------
    # Fullscreen overlay controls
    # ------------------------------------------------------------------

    def _build_overlay(self):
        """Build the fullscreen overlay (placeholder, real one built in fs window)."""
        pass

    def _build_overlay_in(self, parent):
        """Build the fullscreen overlay in the given parent window."""
        if self._overlay is not None:
            return

        self._overlay = tk.Frame(parent, bg=_OVERLAY_BG, height=100)

        # Seek row
        seek_f = tk.Frame(self._overlay, bg=_OVERLAY_BG)
        seek_f.pack(fill="x", padx=20, pady=(10, 2))

        self._ov_time = tk.Label(seek_f, text="0:00 / 0:00", fg="gray60",
                                 bg=_OVERLAY_BG, font=("Arial", 10))
        self._ov_time.pack(side="left")

        self._ov_seek = ctk.CTkSlider(
            seek_f, from_=0, to=1000, height=14,
            command=self._on_seek_drag,
            button_color=("#2196f3", "#2196f3"),
            progress_color=("#1565c0", "#1565c0"),
        )
        self._ov_seek.set(0)
        self._ov_seek.pack(side="left", fill="x", expand=True, padx=8)
        self._ov_seek.bind("<ButtonRelease-1>", self._on_seek_release)

        # Button row
        btn_f = tk.Frame(self._overlay, bg=_OVERLAY_BG)
        btn_f.pack(fill="x", padx=20, pady=(2, 10))

        has_eps = len(self._all_episodes) > 1

        self._ov_prev = ctk.CTkButton(
            btn_f, text="⏮", width=36, height=30,
            font=ctk.CTkFont(size=14), fg_color="transparent",
            hover_color="gray30", text_color="white",
            command=self._play_prev_episode,
            state="normal" if has_eps and self._current_ep_index > 0 else "disabled",
        )
        self._ov_prev.pack(side="left", padx=(0, 2))

        self._ov_play = ctk.CTkButton(
            btn_f, text="II", width=40, height=30,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="transparent", hover_color="gray30", text_color="white",
            command=self._toggle_pause,
        )
        self._ov_play.pack(side="left")

        self._ov_next = ctk.CTkButton(
            btn_f, text="⏭", width=36, height=30,
            font=ctk.CTkFont(size=14), fg_color="transparent",
            hover_color="gray30", text_color="white",
            command=self._play_next_episode,
            state="normal" if has_eps and self._current_ep_index < len(self._all_episodes) - 1 else "disabled",
        )
        self._ov_next.pack(side="left", padx=(2, 4))

        ctk.CTkButton(
            btn_f, text="-10s", width=50, height=30,
            fg_color="transparent", hover_color="gray30", text_color="gray70",
            font=ctk.CTkFont(size=11),
            command=lambda: self._seek_relative(-10),
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            btn_f, text="+10s", width=50, height=30,
            fg_color="transparent", hover_color="gray30", text_color="gray70",
            font=ctk.CTkFont(size=11),
            command=lambda: self._seek_relative(10),
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            btn_f, text="⏭ Intro Atla", width=90, height=30,
            fg_color=("#7b1fa2", "#6a1b9a"), hover_color=("#4a148c", "#4a148c"),
            text_color="white", font=ctk.CTkFont(size=11, weight="bold"),
            command=lambda: self._seek_relative(90),
        ).pack(side="left", padx=(6, 2))

        if has_eps:
            ctk.CTkButton(
                btn_f, text="☰ Bölümler", width=90, height=30,
                fg_color=("#00897b", "#00695c"), hover_color=("#004d40", "#004d40"),
                text_color="white", font=ctk.CTkFont(size=11, weight="bold"),
                command=self._toggle_fs_episode_panel,
            ).pack(side="left", padx=(6, 2))

        ov_vol = ctk.CTkSlider(btn_f, from_=0, to=100, width=80, height=14,
                               command=self._on_volume)
        ov_vol.set(self._vol_slider.get())
        ov_vol.pack(side="left", padx=(12, 4))

        self._ov_title = tk.Label(btn_f, text="", fg="white", bg=_OVERLAY_BG,
                                  font=("Arial", 11, "bold"))
        self._ov_title.pack(side="left", padx=12)

        ctk.CTkButton(
            btn_f, text="Kucult", width=60, height=30,
            fg_color="transparent", hover_color="gray30", text_color="white",
            font=ctk.CTkFont(size=11),
            command=self._toggle_fullscreen,
        ).pack(side="right")

        self._overlay.bind("<Enter>", lambda e: self._cancel_overlay_hide())
        self._overlay.bind("<Leave>", lambda e: self._schedule_overlay_hide())

    def _show_overlay(self):
        if not self._fullscreen or self._overlay is None:
            return
        parent = self.app
        self._overlay.place(in_=parent, relx=0, rely=1.0, relwidth=1.0,
                            anchor="sw", height=100)
        self._overlay.lift()
        self._overlay_visible = True
        self._schedule_overlay_hide()

    def _hide_overlay(self):
        if self._overlay is not None:
            self._overlay.place_forget()
        self._overlay_visible = False

    def _schedule_overlay_hide(self):
        self._cancel_overlay_hide()
        self._overlay_hide_job = self.after(_OVERLAY_HIDE_MS, self._hide_overlay)

    def _cancel_overlay_hide(self):
        if self._overlay_hide_job:
            self.after_cancel(self._overlay_hide_job)
            self._overlay_hide_job = None

    def _on_mouse_move(self, event=None):
        if self._fullscreen:
            if not self._overlay_visible:
                self._show_overlay()
            else:
                self._schedule_overlay_hide()

    def _on_video_click(self, event=None):
        if self._fullscreen:
            if self._overlay_visible:
                self._hide_overlay()
            else:
                self._show_overlay()

    def _sync_overlay(self):
        """Sync overlay controls with current state."""
        if self._overlay is None:
            return
        pos = self._position
        dur = self._duration if self._duration > 0 else 1
        self._ov_time.configure(text=f"{_fmt(pos)} / {_fmt(dur)}")
        if not self._seeking and dur > 0:
            self._ov_seek.set((pos / dur) * 1000)
        txt = ">" if self._is_paused else "II"
        self._ov_play.configure(text=txt)
        ep_text = self._episode.display_name() if self._episode else ""
        title = f"{self._title_str} — {ep_text}" if ep_text else self._title_str
        self._ov_title.configure(text=title[:60])

    # ------------------------------------------------------------------
    # Load & Play
    # ------------------------------------------------------------------

    def load(self, links: List[ExtractorLink], subtitles: List[SubtitleFile],
             title: str = "", episode: Optional[Episode] = None,
             content_url: str = "", api_name: str = "", poster_url: str = "",
             resume_position: float = 0.0,
             all_episodes: Optional[List[Episode]] = None):
        self._stop_current()
        self._links = sorted(links, key=lambda l: l.quality or 0, reverse=True)
        self._subtitles = subtitles
        self._title_str = title
        self._episode = episode
        self._content_url = content_url
        self._api_name = api_name
        self._poster_url = poster_url
        self._current_link_idx = 0
        self._is_paused = False
        self._duration = 0.0
        self._position = 0.0
        self._did_initial_seek = False
        self._loading_episode = False

        if all_episodes is not None:
            self._all_episodes = all_episodes
        self._current_ep_index = self._find_episode_index(episode)

        if resume_position > 0:
            self._resume_position = resume_position
        else:
            self._resume_position = self._load_saved_position()

        ep_text = episode.display_name() if episode else ""
        display = f"{title} — {ep_text}" if ep_text else title
        self._title_label.configure(text=display[:80])
        self._ep_label.configure(text=ep_text[:40])
        self._play_btn.configure(text="II")

        self._update_nav_buttons()

        for w in self._quality_frame.winfo_children():
            w.destroy()
        for w in self._sub_frame.winfo_children():
            w.destroy()

        from data.preferences import Preferences
        pref_quality = Preferences.get_int("player_preferred_quality", 0)
        pref_subtitle = Preferences.get_str("player_preferred_subtitle", "")

        if self._links:
            q_vals = [f"{l.quality}p ({l.source})" for l in self._links]

            best_idx = 0
            if pref_quality > 0:
                best_diff = abs(self._links[0].quality - pref_quality)
                for i, lnk in enumerate(self._links):
                    diff = abs((lnk.quality or 0) - pref_quality)
                    if diff < best_diff:
                        best_diff = diff
                        best_idx = i
            self._current_link_idx = best_idx

            self._quality_var = ctk.StringVar(value=q_vals[best_idx])
            self._quality_menu = ctk.CTkOptionMenu(
                self._quality_frame, values=q_vals, variable=self._quality_var,
                width=160, height=26, command=self._on_quality_change,
            )
            self._quality_menu.pack(side="left")

        if self._subtitles:
            s_vals = ["Kapali"] + [s.lang for s in self._subtitles]
            ctk.CTkLabel(self._sub_frame, text="CC:", font=ctk.CTkFont(size=11),
                         text_color="gray60").pack(side="left", padx=(0, 2))

            initial_sub = "Kapali"
            if pref_subtitle:
                for sv in s_vals:
                    if pref_subtitle.lower() in sv.lower():
                        initial_sub = sv
                        break

            self._sub_menu = ctk.CTkOptionMenu(
                self._sub_frame, values=s_vals,
                width=100, height=26, command=self._on_subtitle_change,
            )
            self._sub_menu.set(initial_sub)
            self._sub_menu.pack(side="left")

        self.app.bind("<Escape>", self._on_escape)
        self.after(100, self._wait_and_play)

    def _wait_and_play(self):
        self._video_frame.update_idletasks()
        w = self._video_frame.winfo_width()
        h = self._video_frame.winfo_height()
        if w < 10 or h < 10:
            self.after(100, self._wait_and_play)
            return
        self._start_playback()

    def _start_playback(self):
        if not self._links:
            return
        link = self._links[self._current_link_idx]

        if not _ensure_mpv():
            self._show_error("libmpv bulunamadi.\nlibmpv-2.dll dosyasini uygulama dizinine koyun.")
            return

        try:
            self._create_player(link)
        except Exception as e:
            print(f"[Player] mpv baslatilamadi: {e}")
            import traceback
            traceback.print_exc()
            self._show_error(f"Oynatici hatasi: {e}")

    def _create_player(self, link: ExtractorLink):
        self._video_frame.update_idletasks()
        wid = str(int(self._video_frame.winfo_id()))
        print(f"[Player] wid={wid}, size={self._video_frame.winfo_width()}x{self._video_frame.winfo_height()}")

        self._player = mpv.MPV(
            wid=wid,
            ytdl=False,
            input_default_bindings=False,
            input_vo_keyboard=False,
            osc=False,
            keep_open="yes",
            idle="yes",
            hwdec="auto-safe",
        )

        if link.headers:
            hdr_parts = [f"{k}: {v}" for k, v in link.headers.items()]
            self._player["http-header-fields"] = hdr_parts
        if link.referer:
            self._player["referrer"] = link.referer

        self._player.volume = int(self._vol_slider.get())

        @self._player.property_observer("duration")
        def _on_duration(_name, value):
            if value and value > 0:
                self._duration = value

        @self._player.property_observer("time-pos")
        def _on_time_pos(_name, value):
            if value is not None:
                self._position = value

        print(f"[Player] Playing: {link.url[:80]}...")
        self._player.play(link.url)

        for sub in self._subtitles:
            try:
                self._player.sub_add(sub.url, title=sub.lang)
            except Exception:
                pass

        self._apply_saved_subtitle_pref()

        if self._resume_position > 2 and not self._did_initial_seek:
            self._did_initial_seek = True
            self.after(1500, lambda: self._safe_seek(self._resume_position))

        self._schedule_ui_update()
        self._schedule_progress_save()

    def _apply_saved_subtitle_pref(self):
        """Apply the saved subtitle preference after playback starts."""
        if not self._player or not self._subtitles:
            return
        from data.preferences import Preferences
        pref = Preferences.get_str("player_preferred_subtitle", "")
        if not pref:
            return
        try:
            self._player.sub_visibility = True
            for i, sub in enumerate(self._subtitles):
                if pref.lower() in sub.lang.lower():
                    self._player.sid = i + 1
                    break
        except Exception:
            pass

    def _load_saved_position(self) -> float:
        if not self._content_url or not self._api_name:
            return 0.0
        try:
            from data.database import Database
            ep_num = self._episode.episode if self._episode else None
            s_num = self._episode.season if self._episode else None
            entry = Database.get_watch_progress(
                self._content_url, self._api_name, ep_num, s_num
            )
            if entry and entry.duration > 0 and (entry.position / entry.duration) < 0.93:
                return entry.position
        except Exception:
            pass
        return 0.0

    def _schedule_progress_save(self):
        if self._save_job:
            self.after_cancel(self._save_job)
        self._save_job = self.after(5000, self._save_progress_tick)

    def _save_progress_tick(self):
        self._save_progress()
        self._save_job = self.after(5000, self._save_progress_tick)

    def _save_progress(self):
        if not self._content_url or not self._api_name:
            return
        if self._duration <= 0 or self._position <= 0:
            return
        try:
            from data.database import Database
            from core.models import WatchHistoryEntry
            import time as _time
            ep = self._episode
            Database.upsert_watch_history(WatchHistoryEntry(
                url=self._content_url,
                api_name=self._api_name,
                name=self._title_str,
                poster_url=self._poster_url or None,
                episode=ep.episode if ep else None,
                season=ep.season if ep else None,
                position=self._position,
                duration=self._duration,
                timestamp=int(_time.time()),
                episode_data=ep.data if ep else None,
                episode_name=ep.display_name() if ep else None,
            ))
        except Exception as e:
            print(f"[Player] Progress save error: {e}")

    # ------------------------------------------------------------------
    # Episode navigation
    # ------------------------------------------------------------------

    def _find_episode_index(self, episode: Optional[Episode]) -> int:
        if episode is None or not self._all_episodes:
            return -1
        for i, ep in enumerate(self._all_episodes):
            if ep.data == episode.data:
                return i
        return -1

    def _update_nav_buttons(self):
        has_eps = len(self._all_episodes) > 1
        can_prev = has_eps and self._current_ep_index > 0
        can_next = has_eps and 0 <= self._current_ep_index < len(self._all_episodes) - 1

        self._prev_btn.configure(
            state="normal" if can_prev else "disabled",
            text_color="white" if can_prev else "gray50",
        )
        self._next_btn.configure(
            state="normal" if can_next else "disabled",
            text_color="white" if can_next else "gray50",
        )
        self._ep_list_btn.configure(
            state="normal" if has_eps else "disabled",
        )

        if hasattr(self, "_ov_prev") and self._overlay is not None:
            self._ov_prev.configure(
                state="normal" if can_prev else "disabled",
                text_color="white" if can_prev else "gray50",
            )
            self._ov_next.configure(
                state="normal" if can_next else "disabled",
                text_color="white" if can_next else "gray50",
            )

    def _play_prev_episode(self):
        if self._loading_episode:
            return
        if self._current_ep_index > 0:
            self._switch_to_episode(self._current_ep_index - 1)

    def _play_next_episode(self):
        if self._loading_episode:
            return
        if 0 <= self._current_ep_index < len(self._all_episodes) - 1:
            self._switch_to_episode(self._current_ep_index + 1)

    def _switch_to_episode(self, index: int):
        if index < 0 or index >= len(self._all_episodes):
            return
        ep = self._all_episodes[index]
        self._loading_episode = True

        self._save_progress()

        from core.api_holder import APIHolder
        api = APIHolder.get_api_by_name(self._api_name)
        if api is None:
            self._loading_episode = False
            return

        self.app.set_status(f"Yükleniyor: {ep.display_name()}...")
        links: List[ExtractorLink] = []
        subs: List[SubtitleFile] = []

        async def _load():
            try:
                await api.load_links(
                    ep.data, is_casting=False,
                    callback=links.append,
                    subtitle_callback=subs.append,
                )
            except Exception as exc:
                print(f"[Player] switch episode load_links error: {exc}")
            return links, subs

        def _done(result):
            lks, ss = result
            self._loading_episode = False
            if not lks:
                self.app.set_status("Bağlantı bulunamadı.")
                return
            self.app.set_status("")
            self.load(
                links=lks, subtitles=ss,
                title=self._title_str, episode=ep,
                content_url=self._content_url, api_name=self._api_name,
                poster_url=self._poster_url, resume_position=0.0,
                all_episodes=self._all_episodes,
            )
            if self._ep_panel_visible:
                self._refresh_episode_panel()

        def _err(e):
            self._loading_episode = False
            self.app.set_status(f"Hata: {e}")
            print(f"[Player] switch episode error: {e}")

        self.app.run_async(_load(), callback=_done, error_callback=_err)

    # ------------------------------------------------------------------
    # Episode panel (normal mode — right side)
    # ------------------------------------------------------------------

    def _toggle_episode_panel(self):
        if self._ep_panel_visible:
            self._hide_episode_panel()
        else:
            self._show_episode_panel()

    def _show_episode_panel(self):
        if self._ep_panel is not None:
            self._ep_panel.destroy()

        self._ep_panel = ctk.CTkFrame(self, width=_EP_PANEL_W,
                                      fg_color=("gray14", "gray10"),
                                      corner_radius=0)
        self._ep_panel.grid(row=1, column=1, sticky="nsew")
        self._ep_panel.grid_propagate(False)
        self.grid_columnconfigure(1, minsize=_EP_PANEL_W)

        self._build_episode_panel_content(self._ep_panel)
        self._ep_panel_visible = True

    def _hide_episode_panel(self):
        if self._ep_panel is not None:
            self._ep_panel.destroy()
            self._ep_panel = None
        self.grid_columnconfigure(1, minsize=0)
        self._ep_panel_visible = False

    def _build_episode_panel_content(self, parent):
        header = ctk.CTkFrame(parent, height=36, fg_color="transparent")
        header.pack(fill="x", padx=8, pady=(8, 4))
        header.pack_propagate(False)

        ctk.CTkLabel(
            header, text="Bölümler",
            font=ctk.CTkFont(size=13, weight="bold"), text_color="white",
        ).pack(side="left")

        ctk.CTkButton(
            header, text="✕", width=28, height=28,
            fg_color="transparent", hover_color="gray30", text_color="gray60",
            font=ctk.CTkFont(size=14), command=self._hide_episode_panel,
        ).pack(side="right")

        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        for i, ep in enumerate(self._all_episodes):
            is_current = (i == self._current_ep_index)
            self._make_ep_row(scroll, ep, i, is_current)

    def _make_ep_row(self, parent, ep: Episode, index: int, is_current: bool):
        fg = ("#1565c0", "#0d47a1") if is_current else ("gray22", "gray18")
        hover = ("#1976d2", "#1565c0") if is_current else ("gray30", "gray25")

        row = ctk.CTkFrame(parent, height=40, fg_color=fg, corner_radius=6)
        row.pack(fill="x", pady=2)
        row.pack_propagate(False)

        name = ep.display_name() or f"Bölüm {index + 1}"
        if ep.name and ep.name != name:
            name = f"{name} — {ep.name[:20]}"

        lbl = ctk.CTkLabel(
            row, text=name[:36],
            font=ctk.CTkFont(size=11, weight="bold" if is_current else "normal"),
            text_color="white" if is_current else "gray70",
            anchor="w",
        )
        lbl.pack(side="left", padx=10, fill="x", expand=True)

        if is_current:
            ctk.CTkLabel(
                row, text="▶", font=ctk.CTkFont(size=12),
                text_color="white", width=20,
            ).pack(side="right", padx=6)

        row.bind("<Button-1>", lambda e, idx=index: self._switch_to_episode(idx))
        lbl.bind("<Button-1>", lambda e, idx=index: self._switch_to_episode(idx))

    def _refresh_episode_panel(self):
        if self._ep_panel is not None and self._ep_panel_visible:
            for w in self._ep_panel.winfo_children():
                w.destroy()
            self._build_episode_panel_content(self._ep_panel)

    # ------------------------------------------------------------------
    # Episode panel (fullscreen — floating)
    # ------------------------------------------------------------------

    def _toggle_fs_episode_panel(self):
        if hasattr(self, "_fs_ep_panel") and self._fs_ep_panel is not None:
            self._hide_fs_episode_panel()
        else:
            self._show_fs_episode_panel()

    def _show_fs_episode_panel(self):
        self._cancel_overlay_hide()

        self._fs_ep_panel = ctk.CTkFrame(
            self.app, width=_EP_PANEL_W,
            fg_color=("gray14", "gray10"), corner_radius=8,
        )
        self._fs_ep_panel.place(
            relx=1.0, rely=0, relheight=1.0,
            anchor="ne", width=_EP_PANEL_W,
        )
        self._fs_ep_panel.lift()

        self._build_fs_ep_content(self._fs_ep_panel)

        self._fs_ep_panel.bind("<Enter>", lambda e: self._cancel_overlay_hide())
        self._fs_ep_panel.bind("<Leave>", lambda e: self._schedule_overlay_hide())

    def _hide_fs_episode_panel(self):
        if hasattr(self, "_fs_ep_panel") and self._fs_ep_panel is not None:
            self._fs_ep_panel.destroy()
            self._fs_ep_panel = None

    def _build_fs_ep_content(self, parent):
        header = ctk.CTkFrame(parent, height=40, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(10, 4))
        header.pack_propagate(False)

        ctk.CTkLabel(
            header, text="Bölümler",
            font=ctk.CTkFont(size=14, weight="bold"), text_color="white",
        ).pack(side="left")

        ctk.CTkButton(
            header, text="✕", width=30, height=30,
            fg_color="transparent", hover_color="gray30", text_color="gray60",
            font=ctk.CTkFont(size=14), command=self._hide_fs_episode_panel,
        ).pack(side="right")

        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        for i, ep in enumerate(self._all_episodes):
            is_current = (i == self._current_ep_index)
            self._make_ep_row(scroll, ep, i, is_current)

    def _show_error(self, msg: str):
        for w in self._video_frame.winfo_children():
            w.destroy()
        lbl = tk.Label(self._video_frame, text=msg, fg="red", bg="black",
                       font=("Arial", 14))
        lbl.place(relx=0.5, rely=0.5, anchor="center")

    # ------------------------------------------------------------------
    # UI Update Loop
    # ------------------------------------------------------------------

    def _schedule_ui_update(self):
        if self._update_job:
            self.after_cancel(self._update_job)
        self._update_job = self.after(500, self._ui_tick)

    def _ui_tick(self):
        if self._player and not self._seeking:
            pos = self._position
            dur = self._duration if self._duration > 0 else 1
            if dur > 0:
                self._seek_bar.set((pos / dur) * 1000)
            self._time_label.configure(text=f"{_fmt(pos)} / {_fmt(dur)}")
            self._play_btn.configure(text=">" if self._is_paused else "II")
            if self._fullscreen:
                self._sync_overlay()
        self._update_job = self.after(500, self._ui_tick)

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------

    def _toggle_pause(self):
        if not self._player:
            return
        try:
            self._player.pause = not self._player.pause
            self._is_paused = self._player.pause
            txt = ">" if self._is_paused else "II"
            self._play_btn.configure(text=txt)
            if self._overlay:
                self._ov_play.configure(text=txt)
        except Exception:
            pass

    def _seek_relative(self, seconds: float):
        if self._player:
            try:
                self._player.seek(seconds, "relative")
            except Exception:
                pass

    def _on_seek_drag(self, value):
        self._seeking = True

    def _on_seek_release(self, event=None):
        if self._player and self._duration > 0:
            val = self._seek_bar.get()
            if self._fullscreen and self._overlay:
                val = self._ov_seek.get()
            pos = (val / 1000) * self._duration
            try:
                self._player.seek(pos, "absolute")
            except Exception:
                pass
        self._seeking = False

    def _on_volume(self, value):
        if self._player:
            try:
                self._player.volume = int(value)
            except Exception:
                pass

    def _on_quality_change(self, label: str):
        try:
            idx = self._quality_menu.cget("values").index(label)
        except (ValueError, AttributeError):
            return
        if idx == self._current_link_idx:
            return

        from data.preferences import Preferences
        Preferences.set("player_preferred_quality", self._links[idx].quality or 0)

        resume_pos = self._position
        self._current_link_idx = idx
        self._stop_player()

        self._did_initial_seek = True
        self._resume_position = 0

        link = self._links[idx]
        try:
            self._create_player(link)
            if resume_pos > 2:
                self.after(1500, lambda: self._safe_seek(resume_pos))
        except Exception as e:
            print(f"[Player] Kalite degistirme hatasi: {e}")

    def _safe_seek(self, pos):
        if self._player:
            try:
                self._player.seek(pos, "absolute")
            except Exception:
                pass

    def _on_subtitle_change(self, lang: str):
        if not self._player:
            return

        from data.preferences import Preferences
        if lang == "Kapali":
            Preferences.set("player_preferred_subtitle", "")
        else:
            Preferences.set("player_preferred_subtitle", lang)

        try:
            if lang == "Kapali":
                self._player.sub_visibility = False
            else:
                self._player.sub_visibility = True
                for i, sub in enumerate(self._subtitles):
                    if sub.lang == lang:
                        self._player.sid = i + 1
                        break
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Fullscreen — transforms the main app window itself
    # ------------------------------------------------------------------

    def _on_escape(self, event=None):
        if self._fullscreen:
            self._toggle_fullscreen()

    def _toggle_fullscreen(self):
        self._fullscreen = not self._fullscreen

        if self._fullscreen:
            self._enter_fullscreen()
        else:
            self._exit_fullscreen()

    def _enter_fullscreen(self):
        self._build_overlay()

        self._saved_geometry = self.app.geometry()
        self._saved_overrideredirect = self.app.overrideredirect()

        # Hide player chrome
        self._top_bar.grid_remove()
        self._controls.grid_remove()

        # Hide app chrome, expand content to fill the whole window
        try:
            self.app.sidebar.grid_remove()
            self.app.status_bar.grid_remove()
            self.app.content.grid_remove()
            self.app.content.place(x=0, y=0, relwidth=1.0, relheight=1.0)
        except Exception:
            pass

        # Make window borderless and cover full screen
        self.app.overrideredirect(True)
        sw = self.app.winfo_screenwidth()
        sh = self.app.winfo_screenheight()
        self.app.geometry(f"{sw}x{sh}+0+0")
        self.app.attributes("-topmost", True)

        self.app.bind("<Escape>", self._on_escape)
        self.app.bind("<space>", self._on_space)

        self._build_overlay_in(self.app)
        self.after(300, self._show_overlay)

    def _exit_fullscreen(self):
        self._hide_overlay()
        self._cancel_overlay_hide()
        self._hide_fs_episode_panel()

        if self._overlay:
            self._overlay.destroy()
            self._overlay = None

        # Restore window
        self.app.attributes("-topmost", False)
        self.app.overrideredirect(False)
        if hasattr(self, "_saved_geometry"):
            self.app.geometry(self._saved_geometry)

        # Restore app chrome
        try:
            self.app.content.place_forget()
            self.app.content.grid(row=0, column=1, sticky="nsew")
            self.app.sidebar.grid(row=0, column=0, sticky="nsew")
            self.app.status_bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        except Exception:
            pass

        # Restore player chrome
        self._top_bar.grid(row=0, column=0, sticky="ew")
        self._controls.grid(row=2, column=0, sticky="ew")

        try:
            self.app.unbind("<space>")
        except Exception:
            pass

    def _on_space(self, event=None):
        self._toggle_pause()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _stop_player(self):
        if self._save_job:
            self.after_cancel(self._save_job)
            self._save_job = None
        if self._update_job:
            self.after_cancel(self._update_job)
            self._update_job = None
        if self._player:
            try:
                self._player.stop()
                self._player.terminate()
            except Exception:
                pass
            self._player = None

    def _stop_current(self):
        self._save_progress()
        if self._fullscreen:
            self._toggle_fullscreen()
        self._cancel_overlay_hide()
        self._hide_episode_panel()
        self._stop_player()
        try:
            self.app.unbind("<Escape>")
        except Exception:
            pass

    def _go_back(self):
        if self._fullscreen:
            self._toggle_fullscreen()
        self._stop_current()
        self.app.go_back()

    def destroy(self):
        self._stop_current()
        self._hide_episode_panel()
        self._hide_fs_episode_panel()
        if self._overlay:
            self._overlay.destroy()
            self._overlay = None
        super().destroy()


def _fmt(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"
