"""M3U8 / HLS playlist parsing helpers."""
from __future__ import annotations
import re
from typing import List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class M3U8Stream:
    url: str
    bandwidth: int = 0
    resolution: Optional[str] = None
    codecs: Optional[str] = None

    def quality(self) -> int:
        if self.resolution:
            m = re.search(r"(\d+)$", self.resolution)
            if m:
                return int(m.group(1))
        if self.bandwidth:
            return self.bandwidth // 1000
        return -1

    def quality_str(self) -> str:
        q = self.quality()
        return f"{q}p" if q > 0 else "Unknown"


def parse_m3u8(content: str, base_url: str = "") -> List[M3U8Stream]:
    """Parse an M3U8 master playlist and return a list of streams."""
    streams: List[M3U8Stream] = []
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXT-X-STREAM-INF:"):
            attrs = _parse_attributes(line[len("#EXT-X-STREAM-INF:"):])
            bandwidth = int(attrs.get("BANDWIDTH", 0))
            resolution = attrs.get("RESOLUTION")
            codecs = attrs.get("CODECS")
            i += 1
            if i < len(lines):
                url = lines[i].strip()
                if not url.startswith("http"):
                    url = _resolve_url(url, base_url)
                streams.append(M3U8Stream(
                    url=url,
                    bandwidth=bandwidth,
                    resolution=resolution,
                    codecs=codecs,
                ))
        i += 1

    streams.sort(key=lambda s: s.bandwidth, reverse=True)
    return streams


def is_master_playlist(content: str) -> bool:
    return "#EXT-X-STREAM-INF" in content


def _parse_attributes(attr_str: str) -> dict:
    attrs = {}
    for match in re.finditer(r'(\w[\w-]*)=(?:"([^"]*)"|([\w@.,/-]+))', attr_str):
        key = match.group(1)
        val = match.group(2) if match.group(2) is not None else match.group(3)
        attrs[key] = val
    return attrs


def _resolve_url(path: str, base: str) -> str:
    if not base:
        return path
    if path.startswith("/"):
        from urllib.parse import urlparse
        p = urlparse(base)
        return f"{p.scheme}://{p.netloc}{path}"
    base_dir = base.rsplit("/", 1)[0]
    return f"{base_dir}/{path}"


def quality_from_url(url: str) -> int:
    """Guess quality from stream URL patterns."""
    patterns = [
        (r"4k|2160p?", 2160), (r"1080p?", 1080), (r"720p?", 720),
        (r"480p?", 480), (r"360p?", 360), (r"240p?", 240),
    ]
    lower = url.lower()
    for pat, q in patterns:
        if re.search(pat, lower):
            return q
    return -1
