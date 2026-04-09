from __future__ import annotations
from abc import ABC
from typing import Optional, List, Callable
from core.models import ExtractorLink, SubtitleFile, ExtractorLinkType
import re


class ExtractorApi(ABC):
    """
    Abstract base class for video link extractors.
    Equivalent to CloudStream's ExtractorApi.
    """

    name: str = "Unknown Extractor"
    main_url: str = ""
    requires_referer: bool = False
    source_plugin: Optional[str] = None

    async def get_url(
        self,
        url: str,
        referer: Optional[str] = None,
        subtitle_callback: Optional[Callable[[SubtitleFile], None]] = None,
        callback: Optional[Callable[[ExtractorLink], None]] = None,
    ) -> Optional[List[ExtractorLink]]:
        """
        Extract video links from the given URL.
        Either call callback() for each link OR return a list.
        """
        return []

    def get_extractor_url(self, url: str) -> str:
        """Transform a raw URL into the final extractor URL."""
        return url

    def can_handle(self, url: str) -> bool:
        """Check if this extractor can handle the given URL."""
        if not self.main_url:
            return False
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            main_parsed = urlparse(self.main_url)
            host = parsed.netloc.lower().lstrip("www.")
            main_host = main_parsed.netloc.lower().lstrip("www.")
            return host == main_host or host.endswith("." + main_host)
        except Exception:
            return self.main_url.lower() in url.lower()

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.name} ({self.main_url})>"


# ---------------------------------------------------------------------------
# Global extractor registry and dispatch
# ---------------------------------------------------------------------------

_extractor_apis: List[ExtractorApi] = []


def register_extractor(extractor: ExtractorApi) -> None:
    """Register an extractor globally."""
    _extractor_apis.append(extractor)


def get_extractor_apis() -> List[ExtractorApi]:
    return list(_extractor_apis)


async def load_extractor(
    url: str,
    referer: Optional[str] = None,
    subtitle_callback: Optional[Callable[[SubtitleFile], None]] = None,
    callback: Optional[Callable[[ExtractorLink], None]] = None,
) -> bool:
    """
    Find an appropriate extractor for the URL and invoke it.
    Returns True if an extractor was found and ran.
    """
    # Exact match first, then fuzzy
    for extractor in reversed(_extractor_apis):
        if extractor.can_handle(url):
            links = await extractor.get_url(
                url, referer, subtitle_callback, callback
            )
            if links and callback:
                for link in links:
                    callback(link)
            return True

    # Fuzzy fallback: substring match
    for extractor in reversed(_extractor_apis):
        if extractor.main_url and extractor.main_url.lower() in url.lower():
            links = await extractor.get_url(
                url, referer, subtitle_callback, callback
            )
            if links and callback:
                for link in links:
                    callback(link)
            return True

    # If nothing matched, treat as direct link
    if callback and (url.endswith(".m3u8") or ".m3u8?" in url):
        callback(ExtractorLink(
            source="Direct",
            name="Direct Stream",
            url=url,
            referer=referer or "",
            type=ExtractorLinkType.M3U8,
            is_m3u8=True,
        ))
        return True
    elif callback and (url.startswith("http") or url.startswith("rtmp")):
        callback(ExtractorLink(
            source="Direct",
            name="Direct Link",
            url=url,
            referer=referer or "",
            type=ExtractorLinkType.VIDEO,
        ))
        return True

    return False
