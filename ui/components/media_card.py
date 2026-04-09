"""
MediaCard — a clickable poster card showing title, type badge, and quality badge.
"""
from __future__ import annotations
import threading
from collections import OrderedDict
from typing import Callable, Optional
import io

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont

from core.models import SearchResponse, TvType, SearchQuality

CARD_WIDTH = 140
CARD_HEIGHT = 220
POSTER_HEIGHT = 190

# ---------------------------------------------------------------------------
# Global LRU image cache  (URL → PIL Image, max ~200 items ≈ 100-150 MB)
# ---------------------------------------------------------------------------
_IMAGE_CACHE_MAX = 200
_image_cache: OrderedDict[str, Image.Image] = OrderedDict()
_cache_lock = threading.Lock()


def _cache_get(url: str) -> Optional[Image.Image]:
    with _cache_lock:
        img = _image_cache.get(url)
        if img is not None:
            _image_cache.move_to_end(url)
        return img


def _cache_put(url: str, img: Image.Image):
    with _cache_lock:
        _image_cache[url] = img
        _image_cache.move_to_end(url)
        while len(_image_cache) > _IMAGE_CACHE_MAX:
            _image_cache.popitem(last=False)

TYPE_COLORS = {
    TvType.Movie: "#e53935",
    TvType.TvSeries: "#1e88e5",
    TvType.Anime: "#8e24aa",
    TvType.OVA: "#7b1fa2",
    TvType.AnimeMovie: "#6a1b9a",
    TvType.Cartoon: "#00897b",
    TvType.Documentary: "#558b2f",
    TvType.AsianDrama: "#f4511e",
    TvType.Live: "#e53935",
}

QUALITY_COLORS = {
    SearchQuality.HD: "#ffa000",
    SearchQuality.FHD: "#f57c00",
    SearchQuality.UHD_4K: "#e65100",
    SearchQuality.CAM: "#546e7a",
}


_PLACEHOLDER_FONT: Optional[ImageFont.FreeTypeFont] = None
_PLACEHOLDER_FONT_LOADED = False


def _get_placeholder_font(size: int = 12) -> Optional[ImageFont.FreeTypeFont]:
    global _PLACEHOLDER_FONT, _PLACEHOLDER_FONT_LOADED
    if _PLACEHOLDER_FONT_LOADED:
        return _PLACEHOLDER_FONT
    _PLACEHOLDER_FONT_LOADED = True
    import sys, os
    candidates = []
    if sys.platform == "win32":
        windir = os.environ.get("WINDIR", r"C:\Windows")
        fonts_dir = os.path.join(windir, "Fonts")
        candidates = [
            os.path.join(fonts_dir, "segoeui.ttf"),
            os.path.join(fonts_dir, "arial.ttf"),
            os.path.join(fonts_dir, "tahoma.ttf"),
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
    for path in candidates:
        try:
            _PLACEHOLDER_FONT = ImageFont.truetype(path, size)
            return _PLACEHOLDER_FONT
        except (OSError, IOError):
            continue
    return None


def _make_placeholder(width: int, height: int, title: str) -> Image.Image:
    img = Image.new("RGB", (width, height), color=(30, 30, 40))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, width, height], outline=(60, 60, 80), width=2)
    font = _get_placeholder_font(12)
    words = title.split()
    lines: list[str] = []
    line = ""
    for w in words:
        if len(line + w) > 14:
            if line:
                lines.append(line.strip())
            line = w + " "
        else:
            line += w + " "
    if line:
        lines.append(line.strip())
    y = height // 2 - len(lines) * 8
    for ln in lines[:4]:
        try:
            draw.text((width // 2, y), ln, fill=(160, 160, 180),
                       anchor="mm", font=font)
        except (UnicodeEncodeError, UnicodeDecodeError):
            safe = ln.encode("ascii", "replace").decode("ascii")
            draw.text((width // 2, y), safe, fill=(160, 160, 180),
                       anchor="mm", font=font)
        y += 16
    return img


class MediaCard(ctk.CTkFrame):
    """
    A poster card widget. Shows poster image, title, type/quality badges.
    Clicking triggers on_click(search_response).
    """

    def __init__(
        self,
        parent,
        result: SearchResponse,
        on_click: Optional[Callable[[SearchResponse], None]] = None,
        width: int = CARD_WIDTH,
        **kwargs,
    ):
        super().__init__(
            parent,
            width=width,
            height=CARD_HEIGHT + 30,
            fg_color="transparent",
            **kwargs,
        )
        self.result = result
        self.on_click = on_click
        self._image_ref = None

        self.pack_propagate(False)
        self._build()
        self._load_image_async()

    def _build(self):
        # Poster frame
        self.poster_frame = ctk.CTkFrame(
            self,
            width=CARD_WIDTH,
            height=POSTER_HEIGHT,
            fg_color=("#2a2a2a", "#1a1a1a"),
            corner_radius=8,
        )
        self.poster_frame.pack(padx=2, pady=(2, 0))
        self.poster_frame.pack_propagate(False)

        self.image_label = ctk.CTkLabel(
            self.poster_frame,
            text="",
            image=None,
        )
        self.image_label.place(relx=0.5, rely=0.5, anchor="center")

        # Type badge
        tv_type = self.result.type
        if tv_type:
            color = TYPE_COLORS.get(tv_type, "#555")
            badge = ctk.CTkLabel(
                self.poster_frame,
                text=tv_type.value[:3].upper(),
                font=ctk.CTkFont(size=9, weight="bold"),
                fg_color=color,
                text_color="white",
                corner_radius=4,
                width=28, height=16,
            )
            badge.place(x=4, y=4)

        # Quality badge
        if self.result.quality and self.result.quality != SearchQuality.Unknown:
            q_color = QUALITY_COLORS.get(self.result.quality, "#555")
            q_badge = ctk.CTkLabel(
                self.poster_frame,
                text=self.result.quality.value,
                font=ctk.CTkFont(size=9, weight="bold"),
                fg_color=q_color,
                text_color="white",
                corner_radius=4,
                width=28, height=16,
            )
            q_badge.place(relx=1.0, x=-4, y=4, anchor="ne")

        # Title
        self.title_label = ctk.CTkLabel(
            self,
            text=self.result.name,
            font=ctk.CTkFont(size=11),
            wraplength=CARD_WIDTH - 4,
            justify="left",
            anchor="w",
        )
        self.title_label.pack(padx=4, pady=(2, 0), fill="x")

        # Bind clicks
        for widget in (self.poster_frame, self.image_label, self.title_label):
            widget.bind("<Button-1>", self._handle_click)
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._handle_click)

    def _handle_click(self, event=None):
        if self.on_click:
            self.on_click(self.result)

    def _on_enter(self, event=None):
        self.poster_frame.configure(border_width=2, border_color="#4fc3f7")

    def _on_leave(self, event=None):
        self.poster_frame.configure(border_width=0)

    def _load_image_async(self):
        url = self.result.poster_url
        if not url:
            self._set_placeholder()
            return

        cached = _cache_get(url)
        if cached is not None:
            self._apply_pil_image(cached)
            return

        from ui.app import CloudStreamApp
        pool = CloudStreamApp.get_image_pool()
        pool.submit(self._fetch_image, url)

    def _fetch_image(self, url: str):
        try:
            import httpx
            resp = httpx.get(url, timeout=10, follow_redirects=True)
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content)).convert("RGB")
            img = img.resize((CARD_WIDTH - 4, POSTER_HEIGHT - 4), Image.LANCZOS)
            _cache_put(url, img)
            self.after(0, lambda: self._apply_pil_image(img))
        except Exception:
            self.after(0, self._set_placeholder)

    def _apply_pil_image(self, img: Image.Image):
        try:
            if not self.winfo_exists():
                return
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img,
                                   size=(CARD_WIDTH - 4, POSTER_HEIGHT - 4))
            self._image_ref = ctk_img
            self.image_label.configure(image=ctk_img, text="")
        except Exception:
            pass

    def _set_placeholder(self):
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        ph = _make_placeholder(CARD_WIDTH - 4, POSTER_HEIGHT - 4, self.result.name)
        ctk_img = ctk.CTkImage(light_image=ph, dark_image=ph,
                               size=(CARD_WIDTH - 4, POSTER_HEIGHT - 4))
        self._image_ref = ctk_img
        try:
            self.image_label.configure(image=ctk_img, text="")
        except Exception:
            pass
