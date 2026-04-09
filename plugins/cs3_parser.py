"""
CS3 Parser - CloudStream .cs3 (ZIP: manifest.json + classes.dex) dosyalarini parse eder.

.cs3 dosyasi bir ZIP arsividir:
  - manifest.json: plugin adi, surumu, sinif adi
  - classes.dex: Dalvik bytecode (Android DEX format)

Bu modul DEX string tablosunu, type/class bilgilerini cikarir
ve stringleri kategorize eder (URL, CSS selektor, header, endpoint, regex, extractor).
"""
from __future__ import annotations

import io
import json
import re
import struct
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set


# ---------------------------------------------------------------------------
# Veri yapilari
# ---------------------------------------------------------------------------

@dataclass
class CS3Manifest:
    plugin_class_name: str = ""
    name: str = ""
    version: int = 0
    requires_resources: bool = False


@dataclass
class CategorizedStrings:
    urls: List[str] = field(default_factory=list)
    selectors: List[str] = field(default_factory=list)
    headers: Dict[str, str] = field(default_factory=dict)
    endpoints: List[str] = field(default_factory=list)
    regex_patterns: List[str] = field(default_factory=list)
    extractor_domains: List[str] = field(default_factory=list)
    main_page_entries: List[str] = field(default_factory=list)
    main_page_labels: List[str] = field(default_factory=list)
    search_endpoints: List[str] = field(default_factory=list)
    api_keys: Dict[str, str] = field(default_factory=dict)


@dataclass
class CS3ParseResult:
    manifest: CS3Manifest
    all_strings: List[str]
    categorized: CategorizedStrings
    class_names: List[str]
    main_class_name: str = ""
    plugin_type: str = "unknown"  # "api", "scraper", "hybrid"
    main_url: str = ""
    tv_types: List[str] = field(default_factory=list)
    provider_fields: Dict[str, object] = field(default_factory=dict)
    api_methods: List[Dict] = field(default_factory=list)
    auth_pattern: str = "none"  # "none", "static_hex_token", "bearer_token", etc.
    auth_details: Dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Bilinen extractor domain'leri  (cs3 dosyalarindan cikarildi)
# ---------------------------------------------------------------------------

KNOWN_EXTRACTORS: Set[str] = {
    "tau-video.xyz", "filemoon.sx", "filemoon.in", "filemoon.to",
    "doodstream.com", "dood.re", "dood.watch", "dood.wf",
    "doply.net", "sibnet.ru", "myvidplay.com", "gdplayer.vip",
    "drive.google.com", "abstream.to", "rubyvidhub.com",
    "bysedikamoum.com", "bysezoxexe.com", "dzen.ru",
    "vidlink.pro", "vidfast.pro", "vidplus.pro", "vidrock.net",
    "vidsrc.cc", "vsembed.ru", "multiembed.mov",
}

KNOWN_HEADER_KEYS: Set[str] = {
    "x-e-h", "X-Requested-With", "Authorization", "Referer",
    "User-Agent", "Cookie", "x-api-key", "Accept",
}

CSS_SELECTOR_PATTERNS = re.compile(
    r"^(div|span|a|article|section|h[1-6]|img|table|tbody|tr|td|ul|li|p|iframe|source|option)"
    r"[.#\[:\s]"
    r"|"
    r"^[.#]\w"
    r"|"
    r"\[(?:href|src|data-|class|id|rel)"
)

TV_TYPE_MAP = {
    "TvSeries": "TvSeries", "Movie": "Movie", "Anime": "Anime",
    "OVA": "OVA", "AnimeMovie": "AnimeMovie", "Cartoon": "Cartoon",
    "Documentary": "Documentary", "AsianDrama": "AsianDrama",
    "Live": "Live", "NSFW": "NSFW",
}


# ---------------------------------------------------------------------------
# DEX okuyucu
# ---------------------------------------------------------------------------

def _read_uleb128(data: bytes, pos: int) -> tuple:
    """ULEB128 kodlu tamsayiyi oku. (deger, yeni_pos) dondurur."""
    result = 0
    shift = 0
    while True:
        b = data[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, pos


def _extract_dex_strings(dex: bytes) -> List[str]:
    """DEX dosyasinin string tablosunu cikarir."""
    if dex[:4] != b"dex\n":
        raise ValueError("Gecersiz DEX magic bytes")

    str_count = struct.unpack_from("<I", dex, 56)[0]
    str_off = struct.unpack_from("<I", dex, 60)[0]

    strings = []
    for i in range(str_count):
        data_off = struct.unpack_from("<I", dex, str_off + i * 4)[0]
        length, pos = _read_uleb128(dex, data_off)
        try:
            s = dex[pos:pos + length].decode("utf-8", errors="replace")
            strings.append(s)
        except Exception:
            strings.append("")
    return strings


def _extract_dex_types(dex: bytes, strings: List[str]) -> List[str]:
    """DEX type ID tablosundan sinif isimlerini cikarir."""
    type_count = struct.unpack_from("<I", dex, 64)[0]
    type_off = struct.unpack_from("<I", dex, 68)[0]

    types = []
    for i in range(type_count):
        str_idx = struct.unpack_from("<I", dex, type_off + i * 4)[0]
        if str_idx < len(strings):
            types.append(strings[str_idx])
    return types


# ---------------------------------------------------------------------------
# String kategorizasyonu
# ---------------------------------------------------------------------------

def _categorize_strings(
    strings: List[str], manifest: CS3Manifest
) -> CategorizedStrings:
    cat = CategorizedStrings()
    plugin_name_lower = manifest.name.lower()

    seen_endpoints: Set[str] = set()

    for s in strings:
        if not s or len(s) < 2 or len(s) > 2000:
            continue

        # SMAP debug bilgisi, Java type descriptor'lari, lambda isimleri atla
        if s.startswith("SMAP\n") or s.startswith("~~") or s.startswith("$i$a$"):
            continue
        if s.startswith("(") and ")" in s and "L" in s:
            continue
        if s.startswith("Lcom/") or s.startswith("Ljava/") or s.startswith("Lkotlin/"):
            continue
        if s.startswith("Ldalvik/") or s.startswith("Lokhttp3/") or s.startswith("Lorg/"):
            continue
        if s.startswith("Landroid/"):
            continue

        # --- URL'ler ---
        if s.startswith("https://") or s.startswith("http://"):
            cat.urls.append(s)
            for domain in KNOWN_EXTRACTORS:
                if domain in s:
                    if domain not in cat.extractor_domains:
                        cat.extractor_domains.append(domain)
                    break
            # API key parametresi iceriyor mu?
            if "api_key=" in s:
                m = re.search(r"api_key=([a-f0-9]+)", s)
                if m:
                    cat.api_keys["api_key"] = m.group(1)
            if "client_key=" in s:
                m = re.search(r"client_key=([a-f0-9]+)", s)
                if m:
                    cat.api_keys["client_key"] = m.group(1)
            continue

        # --- Goreli endpoint'ler ---
        if s.startswith("/") and not s.startswith("//"):
            if s not in seen_endpoints:
                seen_endpoints.add(s)
                # Search endpoint tespiti
                if any(k in s.lower() for k in ["search", "?adi=", "?s=", "?q="]):
                    cat.search_endpoints.append(s)
                # Ana sayfa entry tespiti
                elif any(k in s for k in [
                    "page", "SAYFA", "&s=", "siralama", "catalog",
                    "titles?", "genre=", "type=", "last-episode", "kat=",
                    "onlyStreamable", "keyword=",
                ]):
                    # Duplicate olanları ve sadece path prefix olanları atla
                    if s not in ("/last-episodes",):
                        cat.main_page_entries.append(s)
                else:
                    cat.endpoints.append(s)
            continue

        # --- CSS selektorler ---
        if CSS_SELECTOR_PATTERNS.match(s):
            cat.selectors.append(s)
            continue

        # --- HTTP header key'leri ---
        if s in KNOWN_HEADER_KEYS:
            cat.headers[s] = ""
            continue

        # --- Header value'lari (x-e-h gibi uzun token'lar) ---
        if "==" in s and len(s) > 30 and "." in s and not s.startswith("http") and " " not in s:
            cat.headers["_xeh_token"] = s
            continue

        # --- Regex kaliplari ---
        if any(c in s for c in [r"\(", r"\.", ".*?", r"\d+", "[^"]) and len(s) > 5:
            cat.regex_patterns.append(s)
            continue

        # --- mainPage label'lari (Turkce kategori isimleri) ---
        if _is_main_page_label(s):
            cat.main_page_labels.append(s)

    return cat


def _is_main_page_label(s: str) -> bool:
    """Ana sayfa kategori label'i olup olmadigini tahmin et."""
    if len(s) < 2 or len(s) > 40:
        return False
    turkish_labels = {
        "Yerli", "Aile", "Aksiyon", "Animasyon", "Belgesel", "Bilimkurgu",
        "Biyografi", "Dram", "Drama", "Fantastik", "Gerilim", "Gizem",
        "Komedi", "Korku", "Macera", "Müzik", "Müzikal", "Romantik",
        "Savaş", "Spor", "Suç", "Tarih", "Western", "Yarışma",
        "Son Eklenenler", "Mini Diziler", "Yerli Diziler", "Yabancı Diziler",
        "Asya Dizileri", "Animasyonlar", "Animeler", "Belgeseller",
        "Seriler", "Filmler", "Son Bölümler", "Anime Dizileri", "Anime Filmleri",
        "Reality TV", "Popüler", "Trend", "En Çok İzlenen",
    }
    return s in turkish_labels or (
        s[0].isupper() and " " not in s and s.isalpha() and len(s) < 20
    )


# ---------------------------------------------------------------------------
# Ana parse fonksiyonu
# ---------------------------------------------------------------------------

def parse_cs3(file_path: str) -> CS3ParseResult:
    """
    .cs3 dosyasini parse eder.
    file_path: .cs3 dosyasinin yolu (veya bytes iceren BytesIO).
    """
    path = Path(file_path)
    data = path.read_bytes()
    return parse_cs3_bytes(data, path.stem)


def parse_cs3_bytes(data: bytes, fallback_name: str = "Unknown") -> CS3ParseResult:
    """Ham bytes'dan .cs3 parse eder. Androguard varsa deep parser kullanir."""
    try:
        from plugins.cs3_decompiler import deep_parse_cs3
        result = deep_parse_cs3(data, fallback_name)
        print(f"[CS3Parser] Deep parser kullanildi: {fallback_name}")
        return result
    except ImportError:
        print(f"[CS3Parser] Androguard bulunamadi, legacy parser: {fallback_name}")
    except Exception as e:
        print(f"[CS3Parser] Deep parser hata ({fallback_name}): {e}, legacy parser'a geciliyor")

    return _legacy_parse_cs3_bytes(data, fallback_name)


def _legacy_parse_cs3_bytes(data: bytes, fallback_name: str = "Unknown") -> CS3ParseResult:
    """Eski string-only parser (fallback)."""
    zf = zipfile.ZipFile(io.BytesIO(data))

    # --- manifest.json ---
    manifest = CS3Manifest(name=fallback_name)
    if "manifest.json" in zf.namelist():
        try:
            mdata = json.loads(zf.read("manifest.json").decode("utf-8"))
            manifest = CS3Manifest(
                plugin_class_name=mdata.get("pluginClassName", ""),
                name=mdata.get("name", fallback_name),
                version=mdata.get("version", 0),
                requires_resources=mdata.get("requiresResources", False),
            )
        except Exception as e:
            print(f"[CS3Parser] manifest.json parse hata: {e}")

    # --- classes.dex ---
    if "classes.dex" not in zf.namelist():
        return CS3ParseResult(
            manifest=manifest,
            all_strings=[],
            categorized=CategorizedStrings(),
            class_names=[],
        )

    dex = zf.read("classes.dex")
    all_strings = _extract_dex_strings(dex)
    all_types = _extract_dex_types(dex, all_strings)

    # Sinif isimlerini duz formata cevir (Lcom/kraptor/AnimeciX; -> com.kraptor.AnimeciX)
    class_names = []
    for t in all_types:
        if t.startswith("L") and t.endswith(";"):
            cn = t[1:-1].replace("/", ".")
            class_names.append(cn)

    # Ana sinif adi (manifest'teki pluginClassName'den)
    main_class = manifest.plugin_class_name  # "com.kraptor.AnimeciXPlugin"
    main_class_base = main_class.rsplit(".", 1)[-1] if main_class else ""
    if main_class_base.endswith("Plugin"):
        main_class_base = main_class_base[:-6]  # "AnimeciX"

    # Stringleri kategorize et
    categorized = _categorize_strings(all_strings, manifest)

    # --- Plugin tipini belirle ---
    has_selectors = bool(categorized.selectors)
    has_api_endpoints = any(
        "/secure/" in e or "/api/" in e or "/page/" in e
        for e in categorized.endpoints + categorized.main_page_entries
    )
    has_asp = any(".asp" in e for e in categorized.endpoints + categorized.main_page_entries)

    if has_api_endpoints and not has_selectors:
        plugin_type = "api"
    elif has_selectors and not has_api_endpoints:
        plugin_type = "scraper"
    else:
        plugin_type = "hybrid"

    # --- mainUrl tespiti ---
    main_url = _detect_main_url(manifest.name, categorized.urls, all_strings)

    # --- TvType tespiti ---
    tv_types = _detect_tv_types(all_strings)

    return CS3ParseResult(
        manifest=manifest,
        all_strings=all_strings,
        categorized=categorized,
        class_names=class_names,
        main_class_name=main_class_base or manifest.name,
        plugin_type=plugin_type,
        main_url=main_url,
        tv_types=tv_types,
    )


def _detect_main_url(name: str, urls: List[str], all_strings: List[str]) -> str:
    """Plugin'in ana URL'sini tespit et. Oncelik: Kraptor domain listesi > DEX stringleri."""
    from urllib.parse import urlparse

    domain_from_list = _fetch_domain_from_list(name)
    if domain_from_list:
        return domain_from_list

    name_lower = name.lower()
    skip_domains = {
        "github.com", "githubusercontent.com", "tmdb.org", "themoviedb.org",
        "api.themoviedb.org", "image.tmdb.org", "developer.themoviedb.org",
        "fanart.tv", "tau-video.xyz", "events.animecix.co",
        "opensubtitles-v3.strem.io", "sub.wyzie.ru",
        "hubcloud.foo", "hubdrive.space",
    }
    skip_domains.update(KNOWN_EXTRACTORS)

    def _is_valid_url(u: str) -> bool:
        """Regex, wildcard veya gecersiz karakter iceren URL'leri filtrele."""
        if any(ch in u for ch in ("*", "\\", "[", "]", "(.*)", "(.+)")):
            return False
        parsed = urlparse(u)
        host = parsed.netloc.lower()
        if not host or "." not in host:
            return False
        if any(d in host for d in skip_domains):
            return False
        if any(kw in parsed.path.lower() for kw in (
            "/api_key=", "/discover/", "/3/find/", "/t/p/"
        )):
            return False
        return True

    name_matches = []
    short_path = []
    for u in urls:
        if not _is_valid_url(u):
            continue
        parsed = urlparse(u)
        host = parsed.netloc.lower()
        base = f"{parsed.scheme}://{parsed.netloc}"
        if name_lower in host or host.split(".")[0] in name_lower:
            name_matches.append(base)
        elif parsed.path.count("/") <= 1:
            short_path.append(base)

    if name_matches:
        name_matches.sort(key=len)
        return name_matches[0]
    if short_path:
        short_path.sort(key=len)
        return short_path[0]

    return ""


_DOMAIN_LIST_CACHE: Optional[Dict[str, str]] = None


def _fetch_domain_from_list(name: str) -> str:
    """Kraptor domain listesinden plugin'in guncel domain'ini cek."""
    global _DOMAIN_LIST_CACHE
    if _DOMAIN_LIST_CACHE is None:
        _DOMAIN_LIST_CACHE = {}
        try:
            import httpx
            r = httpx.get(
                "https://raw.githubusercontent.com/Kraptor123/"
                "domainListesi/refs/heads/main/eklenti_domainleri.txt",
                timeout=10, follow_redirects=True,
            )
            if r.status_code == 200:
                for line in r.text.splitlines():
                    line = line.strip()
                    if line.startswith("|") and ":" in line:
                        parts = line[1:].split(":", 1)
                        if len(parts) == 2:
                            _DOMAIN_LIST_CACHE[parts[0].strip().lower()] = parts[1].strip()
        except Exception:
            pass

    return _DOMAIN_LIST_CACHE.get(name.lower(), "")


def _detect_tv_types(all_strings: List[str]) -> List[str]:
    """Desteklenen TvType'lari tespit et."""
    types = set()
    for s in all_strings:
        if s.startswith("TvType.") or s.startswith("TvType$"):
            t = s.split(".", 1)[-1].split("$", 1)[-1]
            if t in TV_TYPE_MAP:
                types.add(TV_TYPE_MAP[t])
        elif s in TV_TYPE_MAP:
            types.add(TV_TYPE_MAP[s])
    # Isme gore fallback
    if not types:
        types.add("TvSeries")
    return sorted(types)
