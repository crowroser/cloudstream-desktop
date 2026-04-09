"""
DownloadsPage — manage active and completed downloads.
"""
from __future__ import annotations
import asyncio
import os
import threading
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

import customtkinter as ctk

from core.models import ExtractorLink, DownloadEntry
from core.i18n import tr
from data.database import Database
from data.preferences import Preferences

if TYPE_CHECKING:
    from ui.app import CloudStreamApp


class _DownloadTask:
    def __init__(self, entry: DownloadEntry):
        self.entry = entry
        self.cancelled = False
        self.thread: Optional[threading.Thread] = None


class _DownloadManager:
    """Singleton download manager."""
    def __init__(self):
        self._tasks: Dict[str, _DownloadTask] = {}
        self._callbacks: List[callable] = []

    def start_download(self, link: ExtractorLink, title: str, episode_name: str = "") -> str:
        download_id = str(uuid.uuid4())[:8]
        dest_dir = Path(Preferences.get_str("download_path", str(Path.home() / "Downloads" / "CloudStream")))
        dest_dir.mkdir(parents=True, exist_ok=True)

        safe_title = "".join(c for c in title if c.isalnum() or c in " -_").strip()[:60]
        ext = ".mp4" if ".mp4" in link.url.lower() else ".mkv"
        file_path = str(dest_dir / f"{safe_title}{ext}")

        entry = DownloadEntry(
            id=download_id, url=link.url, title=title,
            episode_name=episode_name or None,
            file_path=file_path,
            total_bytes=0, downloaded_bytes=0,
            status="queued", timestamp=int(time.time()),
        )
        Database.upsert_download(entry)
        task = _DownloadTask(entry)
        self._tasks[download_id] = task
        task.thread = threading.Thread(
            target=self._download_worker,
            args=(task, link),
            daemon=True,
        )
        task.thread.start()
        self._notify()
        return download_id

    def _download_worker(self, task: _DownloadTask, link: ExtractorLink):
        try:
            import httpx
            entry = task.entry
            entry.status = "downloading"
            Database.upsert_download(entry)
            self._notify()

            headers = dict(link.headers)
            if link.referer:
                headers["Referer"] = link.referer

            with httpx.stream("GET", link.url, headers=headers,
                              follow_redirects=True, timeout=30) as resp:
                resp.raise_for_status()
                entry.total_bytes = int(resp.headers.get("content-length", 0))
                with open(entry.file_path, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=65536):
                        if task.cancelled:
                            break
                        f.write(chunk)
                        entry.downloaded_bytes += len(chunk)
                        Database.upsert_download(entry)
                        self._notify()

            if task.cancelled:
                entry.status = "cancelled"
                try:
                    Path(entry.file_path).unlink(missing_ok=True)
                except Exception:
                    pass
            else:
                entry.status = "completed"
            Database.upsert_download(entry)
        except Exception as e:
            task.entry.status = "failed"
            Database.upsert_download(task.entry)
            print(f"[Download] Error: {e}")
        self._notify()

    def cancel_download(self, download_id: str):
        task = self._tasks.get(download_id)
        if task:
            task.cancelled = True

    def on_update(self, callback: callable):
        self._callbacks.append(callback)

    def _notify(self):
        for cb in self._callbacks:
            try:
                cb()
            except Exception:
                pass


DownloadManager = _DownloadManager()


class DownloadsPage(ctk.CTkFrame):
    def __init__(self, parent, app: "CloudStreamApp", **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.app = app
        self._row_widgets: Dict[str, ctk.CTkFrame] = {}
        self._build()
        DownloadManager.on_update(lambda: self.after(0, self._refresh))

    def _build(self):
        header = ctk.CTkFrame(self, height=52, fg_color=("gray88", "gray14"), corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header, text=tr("Downloads"),
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(side="left", padx=16, pady=12)

        ctk.CTkButton(
            header, text=tr("Open Folder"), width=110, height=32,
            fg_color="transparent", border_width=1, border_color=("gray60", "gray38"),
            text_color=("gray20", "gray90"),
            command=self._open_downloads_folder,
        ).pack(side="right", padx=16, pady=10)

        # Filter tabs
        self.tab_view = ctk.CTkTabview(self, height=36)
        self.tab_view.pack(fill="x", padx=8)
        self.tab_view.add(tr("Active"))
        self.tab_view.add(tr("Completed"))
        self.tab_view.add(tr("Failed"))

        self.tab_view.configure(command=self._refresh)

        # Scrollable list
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True)

        self._refresh()

    def _refresh(self):
        for w in self.scroll.winfo_children():
            w.destroy()

        entries = Database.get_downloads()
        tab = self.tab_view.get()

        active_label = tr("Active")
        completed_label = tr("Completed")

        if tab == active_label:
            shown = [e for e in entries if e.status in ("queued", "downloading", "paused")]
        elif tab == completed_label:
            shown = [e for e in entries if e.status == "completed"]
        else:
            shown = [e for e in entries if e.status in ("failed", "cancelled")]

        if not shown:
            empty_msgs = {
                active_label: tr("No active downloads."),
                completed_label: tr("No completed downloads."),
            }
            msg = empty_msgs.get(tab, tr("No failed downloads."))
            ctk.CTkLabel(
                self.scroll,
                text=msg,
                font=ctk.CTkFont(size=14),
                text_color=("gray50", "gray55"),
            ).pack(pady=60)
            return

        for entry in shown:
            self._build_row(entry)

    def _build_row(self, entry: DownloadEntry):
        row = ctk.CTkFrame(
            self.scroll,
            fg_color=("gray85", "gray22"),
            corner_radius=8, height=72,
        )
        row.pack(fill="x", padx=12, pady=4)
        row.pack_propagate(False)

        # Info
        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True, padx=12, pady=6)

        title_text = entry.title
        if entry.episode_name:
            title_text += f" — {entry.episode_name}"
        ctk.CTkLabel(
            info, text=title_text,
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).pack(anchor="w")

        # Progress bar
        if entry.status == "downloading" and entry.total_bytes > 0:
            progress = entry.downloaded_bytes / entry.total_bytes
            bar = ctk.CTkProgressBar(info, height=6)
            bar.set(progress)
            bar.pack(fill="x", pady=(2, 0))

            mb_done = entry.downloaded_bytes / (1024 * 1024)
            mb_total = entry.total_bytes / (1024 * 1024)
            ctk.CTkLabel(
                info,
                text=f"{mb_done:.1f} / {mb_total:.1f} MB — {progress * 100:.0f}%",
                font=ctk.CTkFont(size=10),
                text_color=("gray50", "gray60"),
                anchor="w",
            ).pack(anchor="w")
        else:
            status_map = {
                "queued": "Kuyrukta",
                "downloading": "İndiriliyor",
                "completed": "Tamamlandı",
                "failed": "Başarısız",
                "cancelled": "İptal edildi",
                "paused": "Duraklatıldı",
            }
            status_text = status_map.get(entry.status, entry.status)
            ctk.CTkLabel(
                info,
                text=f"Durum: {status_text}",
                font=ctk.CTkFont(size=11),
                text_color=("gray50", "gray60"),
                anchor="w",
            ).pack(anchor="w")

        # Action buttons
        btn_frame = ctk.CTkFrame(row, fg_color="transparent")
        btn_frame.pack(side="right", padx=8, pady=8)

        if entry.status in ("queued", "downloading"):
            ctk.CTkButton(
                btn_frame, text=tr("✕ Cancel"), width=80, height=28,
                fg_color=("gray65", "gray30"),
                command=lambda eid=entry.id: self._cancel(eid),
            ).pack()
        elif entry.status == "completed":
            ctk.CTkButton(
                btn_frame, text=tr("▶ Open"), width=80, height=28,
                fg_color="#1a73e8",
                command=lambda fp=entry.file_path: self._open_file(fp),
            ).pack(pady=2)
            ctk.CTkButton(
                btn_frame, text=tr("🗑 Delete"), width=80, height=28,
                fg_color=("gray65", "gray30"),
                command=lambda eid=entry.id, fp=entry.file_path: self._delete(eid, fp),
            ).pack()
        elif entry.status in ("failed", "cancelled"):
            ctk.CTkButton(
                btn_frame, text=tr("🗑 Remove"), width=80, height=28,
                fg_color=("gray65", "gray30"),
                command=lambda eid=entry.id: self._remove(eid),
            ).pack()

    def _cancel(self, download_id: str):
        DownloadManager.cancel_download(download_id)
        self.after(500, self._refresh)

    def _open_file(self, file_path: str):
        if not os.path.exists(file_path):
            self.app.set_status(tr("File not found."))
            return
        import subprocess, sys
        if sys.platform == "win32":
            os.startfile(file_path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", file_path])
        else:
            subprocess.Popen(["xdg-open", file_path])

    def _delete(self, download_id: str, file_path: str):
        Database.delete_download(download_id)
        try:
            Path(file_path).unlink(missing_ok=True)
        except Exception:
            pass
        self._refresh()

    def _remove(self, download_id: str):
        Database.delete_download(download_id)
        self._refresh()

    def _open_downloads_folder(self):
        folder = Preferences.get_str("download_path")
        if not folder:
            return
        Path(folder).mkdir(parents=True, exist_ok=True)
        import subprocess, sys
        if sys.platform == "win32":
            os.startfile(folder)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])
