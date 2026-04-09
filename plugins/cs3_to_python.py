"""
CS3-to-Python Code Generator
=============================
CS3 parse sonuclarindan calisan bir Python plugin dosyasi uretir.

Uc ana sablon var:
  1. Anizium-tarz API (bytecode'dan cikarilan tam header + endpoint)
  2. Kraptor-tarz API (JSON /secure/ endpoint'ler)
  3. Scraper tabanli (HTML + CSS selektor)

Deep parser (androguard) sonuclari varsa, bytecode'dan cikarilan
header pair'leri, main page entry'leri ve endpoint'ler dogrudan kullanilir.
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

from plugins.cs3_parser import CS3ParseResult

CS3_GEN_VERSION = 6


def generate_plugin(parsed: CS3ParseResult) -> str:
    """Parse edilmis CS3 verisinden calisan Python plugin kodu uretir."""
    name = parsed.manifest.name
    cls_name = _sanitize_class_name(parsed.main_class_name or name)
    main_url = parsed.main_url or "https://example.com"

    tv_types = parsed.tv_types or ["TvSeries"]
    tv_type_str = ", ".join(f"TvType.{t}" for t in tv_types)
    sr_cls = _pick_search_response_class(tv_types)
    lr_cls = _pick_load_response_class(tv_types)
    ptype = _primary_type(tv_types)

    has_deep = bool(parsed.provider_fields.get("_header_pairs"))
    headers_code = _format_all_headers(parsed) if has_deep else _format_headers(_build_headers_dict_legacy(parsed))
    main_page_code = _format_main_page_from_pairs(parsed, main_url) if has_deep else _format_main_page(_build_main_page_entries_legacy(parsed, main_url), main_url)
    search_ep = _build_search_endpoint(parsed)

    ep_field = "episodes={'Bolumler': episodes}," if "Anime" in lr_cls else "episodes=episodes,"

    api_style = _detect_api_style(parsed)
    use_api = parsed.plugin_type == "api"

    if not use_api and parsed.plugin_type == "hybrid":
        all_eps = parsed.categorized.endpoints
        api_count = sum(1 for e in all_eps if e.startswith("/api/") or
                        "/secure/" in e or "/discover/" in e)
        if api_count >= 2:
            use_api = True
        elif any(e.startswith("/api/") for e in all_eps):
            use_api = True

    if use_api:
        if api_style == "anizium":
            body = _anizium_api_template(
                cls_name, name, main_url, tv_type_str, sr_cls, lr_cls,
                ptype, headers_code, main_page_code, search_ep, ep_field, parsed,
            )
        else:
            body = _kraptor_api_template(
                cls_name, name, main_url, tv_type_str, sr_cls, lr_cls,
                ptype, headers_code, main_page_code, search_ep, ep_field, parsed,
            )
    else:
        selectors = parsed.categorized.selectors
        dex_cards = _extract_dex_card_selectors(selectors)
        dex_titles = _extract_dex_title_selectors(selectors)
        dex_posters = _extract_dex_poster_selectors(selectors)
        detail_title_sel = _find_selector(selectors, ["div.header", "div.tv-overview h1 a", "h1", "div.page-title h1", "h1.page-title"])
        detail_plot_sel = _find_selector(selectors, ["span#tartismayorum-konu", "div.tv-story p", "div.plot", "p#tv-series-desc", "div.series-profile-summary p"])
        iframe_sel = _find_selector(selectors, ["iframe", "div#video-area iframe", "div#Player iframe", "iframe[src*='epikplayer']", "iframe[src*='dosyaload']"])
        ep_list_sel = _find_selector(selectors, [".series-profile-episode-list li", "ul.episodios li", "div.episode-list a"])
        body = _scraper_template(
            cls_name, name, main_url, tv_type_str, sr_cls, lr_cls,
            ptype, headers_code, main_page_code, search_ep, ep_field,
            dex_cards, dex_titles, dex_posters,
            detail_title_sel, detail_plot_sel, iframe_sel, ep_list_sel,
            parsed,
        )

    return f"# CS3_GEN_V{CS3_GEN_VERSION}\n" + body


# ---------------------------------------------------------------------------
# API style tespiti
# ---------------------------------------------------------------------------

def _detect_api_style(parsed: CS3ParseResult) -> str:
    all_eps = parsed.categorized.endpoints + parsed.categorized.main_page_entries
    ep_str = " ".join(all_eps).lower()
    if "/anime/" in ep_str or "/page/catalog" in ep_str or "/page/search" in ep_str:
        return "anizium"
    if "/secure/" in ep_str or "/discover/" in ep_str:
        return "kraptor"
    if any(e.startswith("/api/") for e in all_eps):
        return "kraptor"
    return "generic"


# ---------------------------------------------------------------------------
# Anizium-style API Template (bytecode'dan cikarilan tam bilgi)
# ---------------------------------------------------------------------------

def _anizium_api_template(cls, name, url, tvt, sr, lr, pt, hdr, mp, sep, epf, parsed):
    ver = parsed.manifest.version
    pcn = parsed.manifest.plugin_class_name

    detail_ep = "/anime/get?id="
    source_ep = "/anime/source?id="
    similar_ep = "/anime/similar?id="
    for ep in parsed.categorized.endpoints:
        if "/get?" in ep or "/detail?" in ep:
            detail_ep = ep
        elif "/source?" in ep:
            source_ep = ep
        elif "/similar?" in ep:
            similar_ep = ep

    return f'''"""
{name} - Otomatik uretilmis Python plugin (CS3 DEX bytecode cevirisi).
Kaynak: {pcn} v{ver}
"""
from __future__ import annotations
import re
from typing import List, Optional, Callable

import httpx

from plugins.base_plugin import BasePlugin
from core.main_api import MainAPI
from core.models import (
    TvType, SearchResponse, {sr}, {lr},
    HomePageList, HomePageResponse, MainPageRequest, MainPageData,
    ExtractorLink, SubtitleFile, Episode, ExtractorLinkType,
)
from plugins.extractors import try_extract

MAIN_URL = "{url}"
_HEADERS = {hdr}


def _client(timeout=20):
    return httpx.Client(follow_redirects=True, timeout=timeout, headers=_HEADERS)


class {cls}Provider(MainAPI):
    name = "{name}"
    main_url = MAIN_URL
    lang = "tr"
    supported_types = [{tvt}]
    has_main_page = True

    main_page = [
{mp}
    ]

    async def get_main_page(self, page: int, request: MainPageRequest) -> HomePageResponse:
        ep = request.data
        if ep in ("", "/"):
            url = f"{{MAIN_URL}}/page/catalog?page={{page}}"
        elif "?" in ep:
            url = f"{{MAIN_URL}}{{ep}}&page={{page}}" if "page=" not in ep else f"{{MAIN_URL}}{{ep}}{{page}}"
        else:
            url = f"{{MAIN_URL}}{{ep}}{{page}}"
        try:
            with _client() as c:
                r = c.get(url)
                if r.status_code in (401, 403):
                    print(f"[{name}] {{request.name}}: HTTP {{r.status_code}}")
                    return HomePageResponse(items=[], has_next=False)
                r.raise_for_status()
                data = r.json()
        except Exception as e:
            print(f"[{name}] getMainPage hata ({{request.name}}): {{e}}")
            return HomePageResponse(items=[], has_next=False)

        raw = data
        for key in ("page", "data", "results", "items"):
            if isinstance(raw, dict) and key in raw:
                inner = raw[key]
                if isinstance(inner, list):
                    raw = inner
                    break
                elif isinstance(inner, dict):
                    raw = inner
        if isinstance(raw, dict):
            for key in ("data", "results", "items"):
                if key in raw and isinstance(raw[key], list):
                    raw = raw[key]
                    break

        items = []
        for a in (raw if isinstance(raw, list) else []):
            title = a.get("name") or a.get("title", "")
            aid = a.get("ID") or a.get("id")
            poster = a.get("poster") or a.get("image")
            if title and aid:
                items.append({sr}(
                    name=title,
                    url=f"{{MAIN_URL}}{detail_ep}{{aid}}",
                    api_name=self.name,
                    poster_url=poster,
                ))

        page_info = data.get("page", data) if isinstance(data, dict) else {{}}
        has_next = page_info.get("next_page") is not None if isinstance(page_info, dict) else False
        return HomePageResponse(items=[HomePageList(name=request.name, list=items)], has_next=has_next)

    async def search(self, query: str) -> List[{sr}]:
        url = f"{{MAIN_URL}}{sep}{{query}}"
        try:
            with _client() as c:
                r = c.get(url)
                r.raise_for_status()
                data = r.json()
        except Exception as e:
            print(f"[{name}] search hata: {{e}}")
            return []

        raw = data
        for key in ("page", "data", "results", "items"):
            if isinstance(raw, dict) and key in raw:
                inner = raw[key]
                if isinstance(inner, list):
                    raw = inner
                    break
                elif isinstance(inner, dict):
                    raw = inner
        if isinstance(raw, dict):
            for key in ("data", "results", "items"):
                if key in raw and isinstance(raw[key], list):
                    raw = raw[key]
                    break

        items = []
        for a in (raw if isinstance(raw, list) else []):
            title = a.get("name") or a.get("title", "")
            aid = a.get("ID") or a.get("id")
            poster = a.get("poster") or a.get("image")
            if title and aid:
                items.append({sr}(
                    name=title,
                    url=f"{{MAIN_URL}}{detail_ep}{{aid}}",
                    api_name=self.name,
                    poster_url=poster,
                ))
        return items

    async def load(self, url: str) -> Optional[{lr}]:
        try:
            with _client() as c:
                r = c.get(url)
                r.raise_for_status()
                data = r.json()
        except Exception as e:
            print(f"[{name}] load hata: {{e}}")
            return None

        td = data.get("data", data)
        anime_id = td.get("ID") or td.get("id", "")
        episodes = []
        for season in td.get("seasons", []):
            snum = season.get("number", 1)
            for ep in season.get("episodes", []):
                ep_num = ep.get("number", 1)
                ep_name = ep.get("name") or f"{{snum}}. Sezon {{ep_num}}. Bolum"
                episodes.append(Episode(
                    data=f"{{anime_id}}|{{snum}}|{{ep_num}}",
                    name=ep_name, season=snum, episode=ep_num,
                ))

        if not episodes and anime_id:
            episodes.append(Episode(
                data=f"{{anime_id}}|1|1",
                name="Izle", season=1, episode=1,
            ))

        genres = []
        for g in td.get("genre", td.get("genres", td.get("tags", []))):
            if isinstance(g, dict):
                genres.append(g.get("name", ""))
            elif isinstance(g, str):
                genres.append(g)

        return {lr}(
            name=td.get("name") or td.get("title", ""), url=url, api_name=self.name,
            type=TvType.{pt},
            poster_url=td.get("poster") or td.get("details_banner"),
            year=td.get("release_year"),
            plot=td.get("overview", ""),
            tags=genres,
            {epf}
        )

    async def load_links(self, data: str, is_casting: bool,
                         callback: Callable[[ExtractorLink], None],
                         subtitle_callback: Callable[[SubtitleFile], None]) -> bool:
        parts = data.split("|")
        anime_id = parts[0].split("id=")[-1].split("/")[-1] if parts else data
        season_num = parts[1] if len(parts) > 1 else "1"
        episode_num = parts[2] if len(parts) > 2 else "1"

        found = False
        subs_added = set()
        for server_id in (1, 2):
            source_url = (
                f"{{MAIN_URL}}{source_ep}{{anime_id}}"
                f"&plan=premium&season={{season_num}}&episode={{episode_num}}&server={{server_id}}"
            )
            try:
                with _client() as c:
                    r = c.get(source_url)
                    if r.status_code != 200:
                        continue
                    resp = r.json()
            except Exception:
                continue

            if resp.get("isError") or not resp.get("success"):
                continue

            for group in resp.get("groups", []):
                group_name = group.get("name", "")
                for item in group.get("items", []):
                    link = item.get("link") or item.get("url", "")
                    if not link:
                        continue
                    quality = item.get("quality", 0)
                    link_type = item.get("type", "mp4")
                    is_direct = any(x in link.lower() for x in (".mp4", ".m3u8", ".mkv", ".webm"))
                    if is_direct:
                        ext_type = ExtractorLinkType.M3U8 if "m3u8" in link_type or ".m3u8" in link else ExtractorLinkType.VIDEO
                        callback(ExtractorLink(
                            source="{name}",
                            name=f"{{group_name}} {{quality}}p",
                            url=link,
                            referer=MAIN_URL + "/",
                            quality=quality,
                            type=ext_type,
                            headers=dict(_HEADERS),
                        ))
                        found = True
                    elif try_extract(link, MAIN_URL + "/", callback, "{name}"):
                        found = True
                    else:
                        callback(ExtractorLink(
                            source="{name}",
                            name=f"{{group_name}} {{quality}}p",
                            url=link,
                            referer=MAIN_URL + "/",
                            quality=quality,
                            type=ExtractorLinkType.VIDEO,
                            headers=dict(_HEADERS),
                        ))
                        found = True

            for sub in resp.get("subtitles", []):
                sub_url = sub.get("link") or sub.get("url", "")
                if sub_url and sub_url not in subs_added:
                    subs_added.add(sub_url)
                    subtitle_callback(SubtitleFile(
                        lang=sub.get("name") or sub.get("group", "Turkce"),
                        url=sub_url,
                    ))

        return found


class {cls}Plugin(BasePlugin):
    def load(self):
        self.register_main_api({cls}Provider())
        print("[{cls}Plugin] Yuklendi")

    def before_unload(self):
        pass
'''


# ---------------------------------------------------------------------------
# Kraptor-style API Template (/secure/ endpoint'ler)
# ---------------------------------------------------------------------------

def _kraptor_api_template(cls, name, url, tvt, sr, lr, pt, hdr, mp, sep, epf, parsed):
    ver = parsed.manifest.version
    pcn = parsed.manifest.plugin_class_name
    return f'''"""
{name} - Otomatik uretilmis Python plugin (CS3 DEX cevirisi).
Kaynak: {pcn} v{ver}
"""
from __future__ import annotations
import re
from typing import List, Optional, Callable

import httpx

from plugins.base_plugin import BasePlugin
from core.main_api import MainAPI
from core.models import (
    TvType, SearchResponse, {sr}, {lr},
    HomePageList, HomePageResponse, MainPageRequest, MainPageData,
    ExtractorLink, SubtitleFile, Episode, ExtractorLinkType,
)
from plugins.extractors import try_extract

MAIN_URL = "{url}"
_HEADERS = {hdr}


def _client(timeout=20):
    return httpx.Client(follow_redirects=True, timeout=timeout, headers=_HEADERS)


class {cls}Provider(MainAPI):
    name = "{name}"
    main_url = MAIN_URL
    lang = "tr"
    supported_types = [{tvt}]
    has_main_page = True

    main_page = [
{mp}
    ]

    async def get_main_page(self, page: int, request: MainPageRequest) -> HomePageResponse:
        ep = request.data
        if ep in ("", "/"):
            url = f"{{MAIN_URL}}/secure/titles?type=series&page={{page}}&perPage=16"
        else:
            sep = "&" if "?" in ep else "?"
            url = f"{{MAIN_URL}}{{ep}}{{sep}}page={{page}}&perPage=16"
        try:
            with _client() as c:
                r = c.get(url)
                if r.status_code in (401, 403):
                    print(f"[{name}] {{request.name}}: HTTP {{r.status_code}}")
                    return HomePageResponse(items=[], has_next=False)
                r.raise_for_status()
                data = r.json()
        except Exception as e:
            print(f"[{name}] getMainPage hata ({{request.name}}): {{e}}")
            return HomePageResponse(items=[], has_next=False)

        raw = data
        for key in ("pagination", "data", "results", "items"):
            if isinstance(raw, dict) and key in raw:
                inner = raw[key]
                if isinstance(inner, list):
                    raw = inner
                    break
                elif isinstance(inner, dict):
                    raw = inner
        if isinstance(raw, dict):
            for key in ("data", "results", "items"):
                if key in raw and isinstance(raw[key], list):
                    raw = raw[key]
                    break

        items = []
        for a in (raw if isinstance(raw, list) else []):
            title = a.get("name") or a.get("title") or a.get("title_name", "")
            tid = a.get("id") or a.get("title_id") or a.get("ID")
            poster = a.get("poster") or a.get("title_poster") or a.get("image")
            if title and tid:
                items.append({sr}(
                    name=title,
                    url=f"{{MAIN_URL}}/secure/titles/{{tid}}?titleId={{tid}}",
                    api_name=self.name,
                    poster_url=poster,
                    year=a.get("year"),
                ))

        has_next = bool(data.get("pagination", {{}}).get("next_page_url") or data.get("next_page_url"))
        return HomePageResponse(items=[HomePageList(name=request.name, list=items)], has_next=has_next)

    async def search(self, query: str) -> List[{sr}]:
        url = f"{{MAIN_URL}}{sep}{{query}}?limit=20"
        try:
            with _client() as c:
                r = c.get(url)
                r.raise_for_status()
                data = r.json()
        except Exception as e:
            print(f"[{name}] search hata: {{e}}")
            return []

        results = data.get("results", data if isinstance(data, list) else [])
        items = []
        for a in results:
            title = a.get("name") or a.get("title", "")
            tid = a.get("id")
            poster = a.get("poster") or a.get("image")
            if title and tid:
                items.append({sr}(
                    name=title,
                    url=f"{{MAIN_URL}}/secure/titles/{{tid}}?titleId={{tid}}",
                    api_name=self.name,
                    poster_url=poster,
                    year=a.get("year"),
                ))
        return items

    async def load(self, url: str) -> Optional[{lr}]:
        tid_m = re.search(r"titleId=(\\d+)", url) or re.search(r"titles/(\\d+)", url)
        if not tid_m:
            return None
        tid = tid_m.group(1)
        api_url = f"{{MAIN_URL}}/secure/titles/{{tid}}?titleId={{tid}}"
        try:
            with _client() as c:
                r = c.get(api_url)
                r.raise_for_status()
                data = r.json()
        except Exception as e:
            print(f"[{name}] load hata: {{e}}")
            return None

        td = data.get("title", data)
        episodes = []
        for season in td.get("seasons", []):
            sn = season.get("number", 1)
            ec = season.get("episode_count", 0)
            try:
                with _client() as c:
                    er = c.get(f"{{MAIN_URL}}/secure/related-videos?episode=1&season={{sn}}&videoId=0&titleId={{tid}}")
                    er.raise_for_status()
                    ed = er.json()
            except Exception:
                for i in range(1, ec + 1):
                    episodes.append(Episode(
                        data=f"{{MAIN_URL}}/secure/best-video?titleId={{tid}}&episode={{i}}&season={{sn}}",
                        name=f"{{sn}}. Sezon {{i}}. Bolum", season=sn, episode=i))
                continue
            for v in ed.get("videos", []):
                eu = v.get("url", "")
                if eu and not eu.startswith("http"):
                    eu = f"{{MAIN_URL}}/{{eu}}"
                en = v.get("episode_num") or v.get("episodeNum")
                snn = v.get("season_num") or v.get("seasonNum") or sn
                episodes.append(Episode(
                    data=eu,
                    name=v.get("description") or v.get("name") or f"{{snn}}. Sezon {{en}}. Bolum",
                    season=snn, episode=en))

        if not td.get("seasons") and td.get("videos"):
            vu = td["videos"][0].get("url", "")
            if vu and not vu.startswith("http"):
                vu = f"{{MAIN_URL}}/{{vu}}"
            episodes.append(Episode(data=vu, name="Izle", season=1, episode=1))

        return {lr}(
            name=td.get("name") or td.get("title", ""), url=url, api_name=self.name,
            type=TvType.{pt}, poster_url=td.get("poster"), year=td.get("year"),
            plot=td.get("description", ""),
            tags=[g.get("display_name", g.get("name", "")) for g in td.get("genres", td.get("tags", []))],
            {epf}
        )

    async def load_links(self, data: str, is_casting: bool,
                         callback: Callable[[ExtractorLink], None],
                         subtitle_callback: Callable[[SubtitleFile], None]) -> bool:
        if not data.startswith("http"):
            data = MAIN_URL + "/" + data.lstrip("/")
        try:
            with _client() as c:
                r = c.get(data)
                final_url = str(r.url)
        except Exception as e:
            print(f"[{name}] loadLinks hata: {{e}}")
            return False
        return try_extract(final_url, MAIN_URL + "/", callback, "{name}")


class {cls}Plugin(BasePlugin):
    def load(self):
        self.register_main_api({cls}Provider())
        print("[{cls}Plugin] Yuklendi")

    def before_unload(self):
        pass
'''


# ---------------------------------------------------------------------------
# Scraper Template
# ---------------------------------------------------------------------------

def _scraper_template(cls, name, url, tvt, sr, lr, pt, hdr, mp, sep, epf,
                      dex_cards, dex_titles, dex_posters,
                      dtitle, dplot, iframe, ep_list_sel, parsed):
    ver = parsed.manifest.version
    pcn = parsed.manifest.plugin_class_name

    dex_card_str = repr(dex_cards) if dex_cards else "[]"
    dex_title_str = repr(dex_titles) if dex_titles else "[]"
    dex_poster_str = repr(dex_posters) if dex_posters else "[]"

    dtitle_list = []
    if dtitle and dtitle != "h1":
        dtitle_list.append(dtitle)
    dtitle_str = repr(dtitle_list) if dtitle_list else "[]"

    dplot_list = []
    if dplot and dplot != "div.plot":
        dplot_list.append(dplot)
    dplot_str = repr(dplot_list) if dplot_list else "[]"

    iframe_list = []
    if iframe and iframe != "iframe":
        iframe_list.append(iframe)
    iframe_str = repr(iframe_list) if iframe_list else "[]"

    ep_list_list = []
    if ep_list_sel and ep_list_sel not in ("a", "div.episodes a[href]"):
        ep_list_list.append(ep_list_sel)
    ep_list_str = repr(ep_list_list) if ep_list_list else "[]"

    return f'''"""
{name} - Otomatik uretilmis Python plugin (CS3 DEX cevirisi).
Kaynak: {pcn} v{ver}
"""
from __future__ import annotations
import re
from typing import List, Optional, Callable, Tuple
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag

from plugins.base_plugin import BasePlugin
from core.main_api import MainAPI
from core.models import (
    TvType, SearchResponse, {sr}, {lr},
    HomePageList, HomePageResponse, MainPageRequest, MainPageData,
    ExtractorLink, SubtitleFile, Episode, ExtractorLinkType,
)
from plugins.extractors import try_extract

MAIN_URL = "{url}"
_HEADERS = {hdr}

_CARD_SELECTORS = {dex_card_str} + [
    "div.poster a", "div.afis a", "a.poster",
    "div.movie-item", "div.film-item", "div.post-item",
    "article.post", "article",
    "div.item", "div.card", "div.result-item",
    "div.col a[href]", "li.item",
    "div.content-box a",
]

_TITLE_SELECTORS = {dex_title_str} + [
    "h2 a", "h3 a", "h2", "h3", "h4",
    "div.title", "div.name", "span.title",
    "div.post-title a", "div.film-name", "div.movie-name",
    "div.description", "div.header",
]

_POSTER_SELECTORS = {dex_poster_str} + [
    "div.poster img", "div.film-poster img", "div.afis img",
    "figure img", "img.film-poster", "img",
]

_DETAIL_TITLE_SELECTORS = {dtitle_str} + [
    "h1", "h2.title", "div.film-name", "div.tv-overview h1 a",
    "div.header", "title",
]

_DETAIL_PLOT_SELECTORS = {dplot_str} + [
    "div.plot", "div.story", "div.description", "div.film-content p",
    "div.tv-story p", "p.description", "span#tartismayorum-konu",
    "div.overview", "meta[name=\\'description\\']",
]

_IFRAME_SELECTORS = {iframe_str} + [
    "iframe[src]",
]

_EP_LIST_SELECTORS = {ep_list_str} + [
    "div.episodes a[href]", "ul.episodes li a[href]",
    "div.season-episodes a[href]", "div.bolumler a[href]",
    "div.episode-list a[href]", "ul.episodios li a[href]",
]


def _client(timeout=20):
    return httpx.Client(follow_redirects=True, timeout=timeout, headers=_HEADERS)


def _fix_url(href):
    if not href:
        return ""
    if href.startswith("http"):
        return href
    return MAIN_URL + ("" if href.startswith("/") else "/") + href


def _img_url(el):
    if el is None:
        return None
    for attr in ("data-src", "src", "data-lazy-src", "data-original", "data-bg"):
        v = el.get(attr)
        if v and not v.endswith((".svg", ".gif")) and "data:image" not in v:
            return _fix_url(v)
    style = el.get("style", "")
    if "url(" in style:
        start = style.index("url(") + 4
        end = style.index(")", start) if ")" in style[style.index("url(") + 4:] else -1
        if end > start:
            url_val = style[start:end].strip().strip("'").strip(chr(34))
            if url_val and not url_val.startswith("data:"):
                return _fix_url(url_val)
    return None


def _find_cards(soup):
    for sel in _CARD_SELECTORS:
        cards = soup.select(sel)
        if len(cards) >= 2:
            return cards
    cards = []
    for a in soup.select("a[href]"):
        if a.find_parent("nav") or a.find_parent("header") or a.find_parent("footer"):
            continue
        if a.select_one("img") and a.get("href", "").startswith(("/", "http")):
            cards.append(a)
    return cards


def _extract_item(el, api_name):
    a_tag = el if el.name == "a" else el.select_one("a[href]")
    if not a_tag or not a_tag.get("href"):
        return None
    href = _fix_url(a_tag.get("href", ""))
    if not href or href == MAIN_URL or href == MAIN_URL + "/":
        return None

    title = ""
    for sel in _TITLE_SELECTORS:
        te = el.select_one(sel)
        if te:
            title = te.get_text(strip=True)
            if title:
                break
    if not title:
        title = a_tag.get("title", "") or a_tag.get("alt", "")
    if not title:
        for child in el.descendants:
            if isinstance(child, str):
                continue
            t = child.get_text(strip=True) if hasattr(child, "get_text") else ""
            if len(t) > 2 and not t.startswith("http"):
                title = t
                break
    if not title:
        title = a_tag.get_text(strip=True)

    purl = None
    for psel in _POSTER_SELECTORS:
        pe = el.select_one(psel)
        if pe:
            purl = _img_url(pe)
            if purl:
                break
    if not purl:
        img = el.select_one("img")
        purl = _img_url(img)
    if not purl:
        for div in el.select("[style*=background]"):
            purl = _img_url(div)
            if purl:
                break

    if not title or len(title) > 200 or not href:
        return None
    return {sr}(name=title[:100], url=href, api_name=api_name, poster_url=purl)


class {cls}Provider(MainAPI):
    name = "{name}"
    main_url = MAIN_URL
    lang = "tr"
    supported_types = [{tvt}]
    has_main_page = True

    main_page = [
{mp}
    ]

    async def get_main_page(self, page: int, request: MainPageRequest) -> HomePageResponse:
        base = request.data
        if not base.startswith("http"):
            base = MAIN_URL.rstrip("/") + ("" if base.startswith("/") else "/") + base
        if "SAYFA" in base:
            url = base.replace("SAYFA", str(page))
        elif "?page=" in base or "&page=" in base:
            url = base
        elif "?" in base:
            url = f"{{base}}&page={{page}}"
        else:
            sep = "" if base.endswith("/") else "/"
            url = f"{{base}}{{sep}}page/{{page}}/" if page > 1 else base
        try:
            with _client() as c:
                r = c.get(url)
                if r.status_code in (401, 403):
                    print(f"[{name}] {{request.name}}: HTTP {{r.status_code}}")
                    return HomePageResponse(items=[], has_next=False)
                r.raise_for_status()
                ct = r.headers.get("content-type", "")
                if "json" in ct:
                    return self._parse_json_main(r.json(), request.name)
                soup = BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            print(f"[{name}] getMainPage hata ({{request.name}}): {{e}}")
            return HomePageResponse(items=[], has_next=False)

        items = []
        for el in _find_cards(soup):
            item = _extract_item(el, self.name)
            if item:
                items.append(item)

        has_next = bool(soup.select_one(
            "a.next, a[rel='next'], li.next a, a.nextpostslink, "
            "div.pagination a:last-child, ul.pagination li:last-child a"
        ))
        return HomePageResponse(items=[HomePageList(name=request.name, list=items)], has_next=has_next)

    def _parse_json_main(self, data, section_name):
        raw = data
        for key in ("page", "pagination", "data", "results", "items"):
            if isinstance(raw, dict) and key in raw:
                inner = raw[key]
                if isinstance(inner, list):
                    raw = inner
                    break
                elif isinstance(inner, dict):
                    raw = inner
        if isinstance(raw, dict):
            for key in ("data", "results", "items"):
                if key in raw and isinstance(raw[key], list):
                    raw = raw[key]
                    break
        if not isinstance(raw, list):
            return HomePageResponse(items=[], has_next=False)

        items = []
        for a in raw:
            if not isinstance(a, dict):
                continue
            title = a.get("name") or a.get("title") or a.get("title_name", "")
            tid = a.get("id") or a.get("ID") or a.get("slug")
            poster = a.get("poster") or a.get("image") or a.get("poster_url") or a.get("thumbnail")
            href = a.get("url") or a.get("href")
            if not href and tid:
                href = f"{{MAIN_URL}}/{{tid}}"
            if title and href:
                items.append({sr}(name=title, url=_fix_url(href), api_name=self.name, poster_url=poster))
        return HomePageResponse(items=[HomePageList(name=section_name, list=items)], has_next=bool(items))

    async def search(self, query: str) -> List[{sr}]:
        url = f"{{MAIN_URL}}{sep}{{query}}"
        try:
            with _client() as c:
                r = c.get(url)
                r.raise_for_status()
                ct = r.headers.get("content-type", "")
                if "json" in ct:
                    resp = self._parse_json_main(r.json(), "search")
                    return resp.items[0].list if resp.items else []
                soup = BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            print(f"[{name}] search hata: {{e}}")
            return []

        results = []
        for el in _find_cards(soup):
            item = _extract_item(el, self.name)
            if item:
                results.append(item)
        return results

    async def load(self, url: str) -> Optional[{lr}]:
        try:
            with _client() as c:
                r = c.get(url)
                r.raise_for_status()
                ct = r.headers.get("content-type", "")
                if "json" in ct:
                    return self._parse_json_detail(r.json(), url)
                soup = BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            print(f"[{name}] load hata: {{e}}")
            return None

        ttl = "Bilinmiyor"
        for sel in _DETAIL_TITLE_SELECTORS:
            te = soup.select_one(sel)
            if te:
                t = te.get_text(strip=True)
                if t and len(t) < 200:
                    ttl = t
                    break

        purl = None
        for sel in _POSTER_SELECTORS:
            img = soup.select_one(sel)
            if img:
                purl = _img_url(img)
                if purl:
                    break

        plot = None
        for sel in _DETAIL_PLOT_SELECTORS:
            pe = soup.select_one(sel)
            if pe:
                if pe.name == "meta":
                    plot = pe.get("content", "")
                else:
                    plot = pe.get_text(strip=True)
                if plot:
                    break

        year = None
        for sel in ["span.year", "div.year", "span.date", "span.color-imdb"]:
            ye = soup.select_one(sel)
            if ye:
                ym = re.search(r"(\\d{{4}})", ye.get_text())
                if ym:
                    y = int(ym.group(1))
                    if 1950 < y < 2035:
                        year = y
                        break

        episodes = []
        ep_containers = []
        for ep_sel in _EP_LIST_SELECTORS:
            ep_containers = soup.select(ep_sel)
            if ep_containers:
                break
        if ep_containers:
            for i, a in enumerate(ep_containers, 1):
                href = a.get("href", "")
                text = a.get_text(strip=True)
                sm = re.search(r"(?:S|Sezon\\s*)(\\d+)", text, re.I)
                em = re.search(r"(?:E|B[öo]l[üu]m\\s*|Ep\\s*)(\\d+)", text, re.I)
                episodes.append(Episode(
                    data=_fix_url(href), name=text or f"Bolum {{i}}",
                    season=int(sm.group(1)) if sm else 1,
                    episode=int(em.group(1)) if em else i))
        else:
            for i, a in enumerate(soup.select("a[href]"), 1):
                href = a.get("href", "")
                text = a.get_text(strip=True).lower()
                if any(k in text for k in ["bolum", "episode", "bölüm", "sezon"]):
                    sm = re.search(r"(\\d+)\\.?\\s*[Ss]ezon", a.get_text(strip=True))
                    em = re.search(r"(\\d+)\\.?\\s*[Bb][öo]l[üu]m", a.get_text(strip=True))
                    episodes.append(Episode(
                        data=_fix_url(href), name=a.get_text(strip=True),
                        season=int(sm.group(1)) if sm else 1,
                        episode=int(em.group(1)) if em else i))

        if not episodes:
            for ifr_sel in _IFRAME_SELECTORS:
                for ifr in soup.select(ifr_sel):
                    src = ifr.get("src", "")
                    if src:
                        episodes.append(Episode(data=_fix_url(src), name="Izle", season=1, episode=1))
                        break
                if episodes:
                    break

        return {lr}(
            name=ttl, url=url, api_name=self.name,
            type=TvType.{pt}, poster_url=purl, year=year, plot=plot,
            {epf}
        )

    def _parse_json_detail(self, data, url):
        td = data.get("data", data.get("title", data))
        if isinstance(td, list) and td:
            td = td[0]
        title = td.get("name") or td.get("title", "Bilinmiyor")
        poster = td.get("poster") or td.get("image") or td.get("poster_url")
        plot = td.get("description") or td.get("overview") or td.get("plot", "")
        year = td.get("year") or td.get("release_year")

        episodes = []
        for season in td.get("seasons", []):
            sn = season.get("number", 1)
            for ep in season.get("episodes", []):
                ep_num = ep.get("number") or ep.get("episode", 1)
                ep_name = ep.get("name") or f"{{sn}}. Sezon {{ep_num}}. Bolum"
                ep_data = ep.get("data") or ep.get("url") or ep.get("id", "")
                episodes.append(Episode(data=str(ep_data), name=ep_name, season=sn, episode=ep_num))

        return {lr}(
            name=title, url=url, api_name=self.name,
            type=TvType.{pt}, poster_url=poster, year=year, plot=plot,
            {epf}
        )

    async def load_links(self, data: str, is_casting: bool,
                         callback: Callable[[ExtractorLink], None],
                         subtitle_callback: Callable[[SubtitleFile], None]) -> bool:
        url = _fix_url(data)
        try:
            with _client() as c:
                r = c.get(url)
                ct = r.headers.get("content-type", "")
                if "json" in ct:
                    jd = r.json()
                    link = jd.get("url") or jd.get("link") or jd.get("source", "")
                    if link:
                        return try_extract(link, MAIN_URL + "/", callback, "{name}")
                soup = BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            print(f"[{name}] loadLinks hata: {{e}}")
            return False

        found = False
        for ifr_sel in _IFRAME_SELECTORS:
            for ifr in soup.select(ifr_sel):
                src = _fix_url(ifr.get("src", ""))
                if src and try_extract(src, MAIN_URL + "/", callback, "{name}"):
                    found = True
        for vid in soup.select("source[src], video source[src]"):
            src = _fix_url(vid.get("src", ""))
            if src:
                quality = 720
                qm = re.search(r"(\\d{{3,4}})p", vid.get("label", ""))
                if qm:
                    quality = int(qm.group(1))
                callback(ExtractorLink(
                    source="{name}", name=f"Direct {{quality}}p", url=src,
                    referer=MAIN_URL + "/", quality=quality,
                    type=ExtractorLinkType.VIDEO, headers=dict(_HEADERS),
                ))
                found = True
        if not found:
            found = try_extract(str(r.url), MAIN_URL + "/", callback, "{name}")
        return found


class {cls}Plugin(BasePlugin):
    def load(self):
        self.register_main_api({cls}Provider())
        print("[{cls}Plugin] Yuklendi")

    def before_unload(self):
        pass
'''


# ---------------------------------------------------------------------------
# Header formatting (deep parser — tum header pair'leri bytecode'dan)
# ---------------------------------------------------------------------------

def _format_all_headers(parsed: CS3ParseResult) -> str:
    pairs = parsed.provider_fields.get("_header_pairs", [])
    if not pairs:
        return _format_headers(_build_headers_dict_legacy(parsed))

    parts = ["{"]
    for key, val in pairs:
        escaped_val = val.replace("\\", "\\\\").replace('"', '\\"')
        parts.append(f'    "{key}": "{escaped_val}",')
    parts.append("}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Main page formatting (deep parser — label:url pair'leri bytecode'dan)
# ---------------------------------------------------------------------------

def _format_main_page_from_pairs(parsed: CS3ParseResult, main_url: str) -> str:
    pairs = parsed.provider_fields.get("_main_page_pairs", [])
    if not pairs:
        return _format_main_page(_build_main_page_entries_legacy(parsed, main_url), main_url)

    lines = []
    for label, url in pairs[:15]:
        lines.append(f'        MainPageData("{label}", "{url}", False),')
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitize_class_name(name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9]", "", name)
    if name and name[0].isdigit():
        name = "P" + name
    return name or "Unknown"


def _pick_search_response_class(tv_types):
    if "Anime" in tv_types:
        return "AnimeSearchResponse"
    if "Movie" in tv_types and "TvSeries" not in tv_types:
        return "MovieSearchResponse"
    return "TvSeriesSearchResponse"


def _pick_load_response_class(tv_types):
    if "Anime" in tv_types:
        return "AnimeLoadResponse"
    if "Movie" in tv_types and "TvSeries" not in tv_types:
        return "MovieLoadResponse"
    return "TvSeriesLoadResponse"


def _primary_type(tv_types):
    if "Anime" in tv_types:
        return "Anime"
    if "Movie" in tv_types:
        return "Movie"
    return "TvSeries"


def _build_headers_dict_legacy(parsed):
    h = {"User-Agent": "_UA", "Referer": "MAIN_URL"}
    cat_h = parsed.categorized.headers
    if "x-e-h" in cat_h:
        token = cat_h.get("_xeh_token", "")
        if token:
            h["x-e-h"] = token
    if "X-Requested-With" in cat_h:
        h["X-Requested-With"] = "XMLHttpRequest"
    return h


def _format_headers(headers):
    parts = ["{"]
    for k, v in headers.items():
        if v == "_UA":
            parts.append('    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",')
        elif v == "MAIN_URL":
            parts.append('    "Referer": MAIN_URL + "/",')
        else:
            parts.append(f'    "{k}": "{v}",')
    parts.append("}")
    return "\n".join(parts)


_LABEL_MAP = {
    "action": "Aksiyon", "comedy": "Komedi", "drama": "Dram",
    "romance": "Romantik", "thriller": "Gerilim", "mystery": "Gizem",
    "series": "Diziler", "movie": "Filmler", "movies": "Filmler",
    "ecchi": "Ecchi", "harem": "Harem", "isekai": "Isekai",
    "magic": "Sihir", "military": "Askeriye", "school": "Okul",
    "seinen": "Seinen", "shoujo": "Shoujo", "shounen": "Shounen",
    "sport": "Spor", "last-episode": "Son Bolumler",
    "last-episodes": "Son Bolumler", "last-added": "Son Eklenenler",
    "favorite": "Favoriler", "top": "Populer",
    "type=series": "Diziler", "type=movie": "Filmler",
    "kat=1": "Yabanci Diziler", "kat=2": "Yerli Diziler",
    "kat=3": "Asya Dizileri", "kat=4": "Animasyonlar",
    "kat=5": "Animeler", "kat=6": "Belgeseller",
    "siralama_tipi=id&s=": "Son Eklenenler",
    "tur[0]=aile": "Aile", "tur[0]=aksiyon": "Aksiyon",
    "tur[0]=animasyon": "Animasyon", "tur[0]=belgesel": "Belgesel",
    "tur[0]=bilimkurgu": "Bilimkurgu", "tur[0]=dram": "Dram",
    "tur[0]=fantastik": "Fantastik", "tur[0]=gerilim": "Gerilim",
    "tur[0]=gizem": "Gizem", "tur[0]=komedi": "Komedi",
    "tur[0]=korku": "Korku", "tur[0]=macera": "Macera",
    "tur[0]=romantik": "Romantik", "tur[0]=spor": "Spor",
    "tur[0]=tarih": "Tarih", "tur[0]=western": "Western",
    "ulke[]=turkiye": "Yerli",
    "aile": "Aile", "aksiyon": "Aksiyon", "aksiyon-macera": "Aksiyon-Macera",
    "animasyon": "Animasyon", "belgesel": "Belgesel", "bilim-kurgu": "Bilim Kurgu",
    "bilim-kurgu-fantazi": "Bilim Kurgu", "dram": "Dram", "gizem": "Gizem",
    "komedi": "Komedi", "korku": "Korku", "macera": "Macera",
    "savas-politik": "Savas-Politik", "suc": "Suc",
    "diziler": "Diziler", "filmler": "Filmler",
    "home": "Ana Sayfa", "tv": "TV",
}

_TR_CATEGORY_LABELS = {
    "Yerli", "Aile", "Aksiyon", "Animasyon", "Belgesel", "Bilimkurgu",
    "Biyografi", "Dram", "Drama", "Fantastik", "Gerilim", "Gizem",
    "Komedi", "Korku", "Macera", "Müzik", "Müzikal", "Romantik",
    "Savaş", "Spor", "Suç", "Tarih", "Western", "Yarışma",
    "Son Eklenenler", "Mini Diziler", "Yerli Diziler", "Yabancı Diziler",
    "Asya Dizileri", "Animasyonlar", "Animeler", "Belgeseller",
    "Seriler", "Filmler", "Son Bölümler", "Anime Dizileri", "Anime Filmleri",
    "Reality TV", "Popüler", "Trend", "En Çok İzlenen",
}


def _label_from_path(ep: str) -> str:
    """Endpoint path'inden okunabilir bir kategori etiketi cikar."""
    ep_lower = ep.lower()
    for key, val in _LABEL_MAP.items():
        if key in ep_lower:
            return val
    path_part = ep.split("?")[0].strip("/")
    if not path_part:
        return ""
    segments = path_part.split("/")
    last = segments[-1]
    for skip in ("tur", "genre", "category", "page", "type"):
        if last == skip and len(segments) >= 2:
            last = segments[-2]
            break
    label = last.replace("-", " ").replace("_", " ").strip().title()
    return label if len(label) > 1 else ""


def _build_main_page_entries_legacy(parsed, main_url):
    entries = parsed.categorized.main_page_entries
    seen_labels: set = set()
    result = []

    def _add(label, ep):
        if label in seen_labels:
            return
        seen_labels.add(label)
        result.append((label, ep))

    for ep in entries:
        label = _label_from_path(ep)
        if label:
            _add(label, ep)

    endpoints = parsed.categorized.endpoints
    for ep in endpoints:
        if any(ch in ep for ch in ("*", "\\", "[", "]")):
            continue
        if "api_key=" in ep or "video_id=" in ep:
            continue
        parts = ep.strip("/").split("/")
        if len(parts) >= 2 and parts[0] in ("dizi", "film", "diziler", "filmler",
                                              "anime", "series", "movies"):
            label = _label_from_path(ep)
            if label and len(label) > 1:
                _add(label, ep)

    cat_labels = parsed.categorized.main_page_labels
    for lbl in cat_labels:
        if lbl in _TR_CATEGORY_LABELS and lbl not in seen_labels:
            slug = lbl.lower().replace(" ", "-").replace("ü", "u").replace("ö", "o") \
                .replace("ş", "s").replace("ç", "c").replace("ğ", "g").replace("ı", "i")
            _add(lbl, f"/{slug}/")

    if not result:
        result.append(("Ana Sayfa", "/"))

    return result[:15]


def _format_main_page(entries, main_url):
    lines = []
    for label, ep in entries[:15]:
        if ep.startswith("http"):
            lines.append(f'        MainPageData("{label}", "{ep}", False),')
        else:
            lines.append(f'        MainPageData("{label}", "{ep}", False),')
    if not lines:
        lines.append(f'        MainPageData("Ana Sayfa", "/", False),')
    return "\n".join(lines)


def _build_search_endpoint(parsed):
    eps = parsed.categorized.search_endpoints
    if eps:
        ep = eps[0]
        return ep if "?" in ep else ep.rstrip("/") + "/"
    return "/?s="


def _find_selector(selectors, candidates):
    for c in candidates:
        for s in selectors:
            if (c in s or s.startswith(c.split("[")[0])) and _is_css_selector(s):
                return s
    return candidates[0] if candidates else "a"


def _is_css_selector(s: str) -> bool:
    """Verilen stringin gecerli bir CSS selektoru olup olmadigini tahmin et."""
    if not s or len(s) < 2 or len(s) > 120:
        return False
    if s.startswith("http") or s.startswith("/") or s.startswith("data:"):
        return False
    if any(ch in s for ch in ("\n", "\t", "()", "{}", "function", "»", "->", ".m3u8", ".json", ".ts", ".txt", ".jpg")):
        return False
    if "=" in s and "[" not in s:
        return False
    if s.startswith(".") or s.startswith("#") or s.startswith("div") or \
       s.startswith("ul") or s.startswith("li") or s.startswith("a") or \
       s.startswith("span") or s.startswith("h1") or s.startswith("h2") or \
       s.startswith("h3") or s.startswith("h4") or s.startswith("h5") or \
       s.startswith("h6") or s.startswith("article") or s.startswith("img") or \
       s.startswith("iframe") or s.startswith("p") or s.startswith("figure"):
        return True
    if " " in s and any(c in s for c in (".", "#", "[", ">")):
        return True
    return False


def _extract_dex_card_selectors(selectors: list) -> list:
    """DEX selektorlerinden kart (card) icin uygun olanlari cikar."""
    card_keywords = ("poster", "item", "card", "result", "film", "movie",
                     "dizi", "content-box", "afis", "figure", "asisotope",
                     "ajax_post", "filter-result", "slider-item", "tray")
    found = []
    for s in selectors:
        if not _is_css_selector(s):
            continue
        s_lower = s.lower()
        if any(kw in s_lower for kw in card_keywords):
            if "img" not in s_lower and "profile" not in s_lower:
                found.append(s)
    return found


def _extract_dex_title_selectors(selectors: list) -> list:
    """DEX selektorlerinden baslik (title) icin uygun olanlari cikar."""
    title_keywords = ("title", "name", "header", "truncate", "subject")
    found = []
    for s in selectors:
        if not _is_css_selector(s):
            continue
        s_lower = s.lower()
        if any(kw in s_lower for kw in title_keywords):
            if "poster" not in s_lower and "img" not in s_lower:
                found.append(s)
    return found


def _extract_dex_poster_selectors(selectors: list) -> list:
    """DEX selektorlerinden poster/gorsel icin uygun olanlari cikar."""
    poster_keywords = ("poster", "image", "img", "thumb", "cover", "afis")
    found = []
    for s in selectors:
        if not _is_css_selector(s):
            continue
        s_lower = s.lower()
        if any(kw in s_lower for kw in poster_keywords):
            found.append(s)
    return found
