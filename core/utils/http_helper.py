"""
HTTP helper — wraps httpx with session management, Cloudflare bypass,
cookie persistence and common header presets.
"""
from __future__ import annotations
import asyncio
import json
import os
import re
from typing import Any, Dict, Optional
from pathlib import Path

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

try:
    import cloudscraper
    CLOUDSCRAPER_AVAILABLE = True
except ImportError:
    CLOUDSCRAPER_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_USER_DATA = Path(os.path.expanduser("~")) / ".cloudstream-desktop"
COOKIE_JAR_PATH = _USER_DATA / "cookies.json"


# ---------------------------------------------------------------------------
# Async HTTP client (httpx) — one client per event loop
# ---------------------------------------------------------------------------

_clients: Dict[int, "httpx.AsyncClient"] = {}


def _get_async_client() -> "httpx.AsyncClient":
    loop = asyncio.get_running_loop()
    loop_id = id(loop)
    client = _clients.get(loop_id)
    if client is None or client.is_closed:
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx is not installed. Run: pip install httpx")
        client = httpx.AsyncClient(
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_connections=30, max_keepalive_connections=15),
        )
        _clients[loop_id] = client
    return client


async def get(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict] = None,
    cookies: Optional[Dict] = None,
    referer: Optional[str] = None,
) -> "httpx.Response":
    """Async GET request."""
    client = _get_async_client()
    h = dict(DEFAULT_HEADERS)
    if headers:
        h.update(headers)
    if referer:
        h["Referer"] = referer
    return await client.get(url, headers=h, params=params, cookies=cookies)


async def post(
    url: str,
    data: Optional[Any] = None,
    json_data: Optional[Any] = None,
    headers: Optional[Dict[str, str]] = None,
    cookies: Optional[Dict] = None,
) -> "httpx.Response":
    """Async POST request."""
    client = _get_async_client()
    h = dict(DEFAULT_HEADERS)
    if headers:
        h.update(headers)
    return await client.post(url, data=data, json=json_data, headers=h, cookies=cookies)


async def get_text(url: str, **kwargs) -> str:
    resp = await get(url, **kwargs)
    resp.raise_for_status()
    return resp.text


async def get_json(url: str, **kwargs) -> Any:
    resp = await get(url, **kwargs)
    resp.raise_for_status()
    return resp.json()


async def post_json(url: str, **kwargs) -> Any:
    resp = await post(url, **kwargs)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Cloudscraper (synchronous, for Cloudflare-protected sites)
# ---------------------------------------------------------------------------

_scraper = None


def get_scraper():
    global _scraper
    if _scraper is None:
        if not CLOUDSCRAPER_AVAILABLE:
            if REQUESTS_AVAILABLE:
                import requests
                s = requests.Session()
                s.headers.update(DEFAULT_HEADERS)
                return s
            raise RuntimeError("cloudscraper or requests not installed.")
        _scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )
        _scraper.headers.update(DEFAULT_HEADERS)
    return _scraper


async def cf_get(url: str, headers: Optional[Dict] = None, **kwargs) -> str:
    """GET with Cloudflare bypass (runs scraper in thread pool)."""
    loop = asyncio.get_event_loop()

    def _sync_get():
        s = get_scraper()
        h = dict(DEFAULT_HEADERS)
        if headers:
            h.update(headers)
        r = s.get(url, headers=h, **kwargs)
        r.raise_for_status()
        return r.text

    return await loop.run_in_executor(None, _sync_get)


async def cf_post(url: str, data: Any = None, headers: Optional[Dict] = None, **kwargs) -> str:
    """POST with Cloudflare bypass."""
    loop = asyncio.get_event_loop()

    def _sync_post():
        s = get_scraper()
        h = dict(DEFAULT_HEADERS)
        if headers:
            h.update(headers)
        r = s.post(url, data=data, headers=h, **kwargs)
        r.raise_for_status()
        return r.text

    return await loop.run_in_executor(None, _sync_post)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def fix_url(url: str, base: str) -> str:
    """Make a potentially relative URL absolute."""
    if url.startswith("http"):
        return url
    if url.startswith("//"):
        scheme = "https:" if "https" in base else "http:"
        return scheme + url
    if url.startswith("/"):
        from urllib.parse import urlparse
        p = urlparse(base)
        return f"{p.scheme}://{p.netloc}{url}"
    return base.rstrip("/") + "/" + url


def parse_cookies(cookie_str: str) -> Dict[str, str]:
    """Parse a cookie header string into a dict."""
    cookies = {}
    for part in cookie_str.split(";"):
        if "=" in part:
            k, v = part.strip().split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies


async def close() -> None:
    """Close all async clients (call on app exit)."""
    for client in list(_clients.values()):
        if not client.is_closed:
            try:
                await client.aclose()
            except Exception:
                pass
    _clients.clear()
