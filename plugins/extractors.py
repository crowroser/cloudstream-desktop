"""
Bilinen video hosting siteleri icin extractor fonksiyonlari.
CS3 DEX stringlerinden tespit edilen extractor domain'leri burada karsilanir.

Her extractor fonksiyonu bir embed URL alir ve callback ile ExtractorLink dondurur.
"""
from __future__ import annotations
import re
from typing import Callable

import httpx

from core.models import ExtractorLink, ExtractorLinkType

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

QUALITY_MAP = {"1080p": 1080, "720p": 720, "480p": 480, "360p": 360}


# ---------------------------------------------------------------------------
# TauVideo  (animecix, anizium vs.)
# ---------------------------------------------------------------------------

def extract_tau_video(
    embed_url: str,
    referer: str,
    callback: Callable[[ExtractorLink], None],
    api_key: str = "1b6b30a5f8d1f2e001b3e4bab00cc6e8",
    client_key: str = "e4a8e5c6400f39ed8ba07d546b90237f",
) -> bool:
    tau_id = re.search(r"/embed/([a-f0-9]+)", embed_url)
    vid = re.search(r"vid=(\d+)", embed_url)
    if not (tau_id and vid):
        return False

    api_url = (
        f"https://tau-video.xyz/api/video/{tau_id.group(1)}"
        f"?vid={vid.group(1)}&api_key={api_key}&client_key={client_key}"
    )
    try:
        with httpx.Client(timeout=12, follow_redirects=True) as c:
            r = c.get(api_url, headers={"User-Agent": _UA, "Referer": "https://tau-video.xyz/"})
            if r.status_code != 200:
                return False
            data = r.json()
    except Exception:
        return False

    for item in data.get("urls", []):
        url = item.get("url", "")
        label = item.get("label", "?")
        if url:
            callback(ExtractorLink(
                source="TauVideo",
                name=f"TauVideo {label}",
                url=url,
                referer="https://tau-video.xyz/",
                quality=QUALITY_MAP.get(label, -1),
                type=ExtractorLinkType.VIDEO,
            ))
    return True


# ---------------------------------------------------------------------------
# Genel iframe => m3u8/mp4 cikarici
# ---------------------------------------------------------------------------

def extract_generic_iframe(
    iframe_url: str,
    referer: str,
    callback: Callable[[ExtractorLink], None],
    source_name: str = "Stream",
) -> bool:
    try:
        with httpx.Client(timeout=15, follow_redirects=True,
                          headers={"User-Agent": _UA, "Referer": referer}) as c:
            r = c.get(iframe_url)
            html = r.text
    except Exception:
        return False

    found = False
    for m in re.finditer(r'"(https?://[^"]+\.m3u8[^"]*)"', html):
        callback(ExtractorLink(
            source=source_name, name="HLS Stream",
            url=m.group(1), referer=iframe_url,
            quality=-1, type=ExtractorLinkType.M3U8,
        ))
        found = True

    if not found:
        for m in re.finditer(r'"(https?://[^"]+\.mp4[^"]*)"', html):
            callback(ExtractorLink(
                source=source_name, name="MP4",
                url=m.group(1), referer=iframe_url,
                quality=-1, type=ExtractorLinkType.VIDEO,
            ))
            found = True

    return found


# ---------------------------------------------------------------------------
# Filemoon
# ---------------------------------------------------------------------------

def extract_filemoon(
    embed_url: str,
    referer: str,
    callback: Callable[[ExtractorLink], None],
) -> bool:
    try:
        with httpx.Client(timeout=15, follow_redirects=True,
                          headers={"User-Agent": _UA, "Referer": referer}) as c:
            r = c.get(embed_url)
            html = r.text
    except Exception:
        return False

    # Filemoon genelde eval-packed JS icerir, ama m3u8 dogrudan HTML'de olabilir
    for m in re.finditer(r'"(https?://[^"]+\.m3u8[^"]*)"', html):
        callback(ExtractorLink(
            source="Filemoon", name="Filemoon HLS",
            url=m.group(1), referer=embed_url,
            quality=-1, type=ExtractorLinkType.M3U8,
        ))
        return True

    # file: 'url' formati
    fm = re.search(r"file:\s*'(https?://[^']+)'", html)
    if fm:
        url = fm.group(1)
        ltype = ExtractorLinkType.M3U8 if ".m3u8" in url else ExtractorLinkType.VIDEO
        callback(ExtractorLink(
            source="Filemoon", name="Filemoon",
            url=url, referer=embed_url,
            quality=-1, type=ltype,
        ))
        return True

    return False


# ---------------------------------------------------------------------------
# DoodStream
# ---------------------------------------------------------------------------

def extract_doodstream(
    embed_url: str,
    referer: str,
    callback: Callable[[ExtractorLink], None],
) -> bool:
    import time
    try:
        # /e/ -> /d/ donusumu
        url = re.sub(r"/(e|d|v|f)/", "/e/", embed_url)
        with httpx.Client(timeout=15, follow_redirects=True,
                          headers={"User-Agent": _UA, "Referer": referer}) as c:
            r = c.get(url)
            html = r.text
    except Exception:
        return False

    # pass_md5 URL'sini bul
    md5_match = re.search(r"(https?://[^/]+/pass_md5/[^'\"]+)", html)
    if not md5_match:
        return False

    try:
        with httpx.Client(timeout=10, follow_redirects=True,
                          headers={"User-Agent": _UA, "Referer": url}) as c:
            r2 = c.get(md5_match.group(1))
            direct = r2.text.strip()
    except Exception:
        return False

    if direct and direct.startswith("http"):
        video_url = f"{direct}zUEJhxc3v2MRdp?token=abcdef&expiry={int(time.time() * 1000)}"
        callback(ExtractorLink(
            source="DoodStream", name="DoodStream",
            url=video_url, referer="https://doodstream.com/",
            quality=-1, type=ExtractorLinkType.VIDEO,
        ))
        return True

    return False


# ---------------------------------------------------------------------------
# Dispatch: domain -> extractor
# ---------------------------------------------------------------------------

EXTRACTOR_MAP = {
    "tau-video.xyz": extract_tau_video,
    "filemoon.sx": extract_filemoon,
    "filemoon.in": extract_filemoon,
    "filemoon.to": extract_filemoon,
    "doodstream.com": extract_doodstream,
    "dood.re": extract_doodstream,
    "dood.watch": extract_doodstream,
    "dood.wf": extract_doodstream,
    "doply.net": extract_doodstream,
}


def try_extract(
    url: str,
    referer: str,
    callback: Callable[[ExtractorLink], None],
    source_name: str = "Stream",
) -> bool:
    """URL'nin domain'ine gore uygun extractor'u calistir."""
    url_lower = url.lower()
    for domain, extractor_fn in EXTRACTOR_MAP.items():
        if domain in url_lower:
            return extractor_fn(url, referer, callback)
    return extract_generic_iframe(url, referer, callback, source_name)
