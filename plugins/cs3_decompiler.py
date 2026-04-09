"""
CS3 Deep Decompiler — Androguard ile DEX bytecode analizi.

classes.dex icindeki Dalvik bytecode'u tam olarak analiz eder:
  - Sinif hiyerarsisi (MainAPI alt sinifi tespiti)
  - Field degerleri (mainUrl, name, lang, headers vb.)
  - Constructor'daki header pair'leri ve mainPage entry'leri
  - Method'lardaki string referanslari (endpoint, search URL vb.)
  - Token / auth mekanizmasi tespiti
"""
from __future__ import annotations

import logging
logging.getLogger("androguard").setLevel(logging.WARNING)

try:
    from loguru import logger as _loguru_logger
    _loguru_logger.disable("androguard")
except ImportError:
    pass

import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from plugins.cs3_parser import (
    CS3Manifest,
    CS3ParseResult,
    CategorizedStrings,
    KNOWN_EXTRACTORS,
    TV_TYPE_MAP,
    _fetch_domain_from_list,
)


# ---------------------------------------------------------------------------
# Veri yapilari
# ---------------------------------------------------------------------------

@dataclass
class ProviderField:
    name: str
    type_desc: str
    value: Any = None


@dataclass
class MethodInfo:
    name: str
    descriptor: str
    strings: List[str] = field(default_factory=list)
    invoked_methods: List[str] = field(default_factory=list)
    http_urls: List[str] = field(default_factory=list)


@dataclass
class DecompiledProvider:
    class_name: str = ""
    super_class: str = ""
    fields: Dict[str, ProviderField] = field(default_factory=dict)
    methods: Dict[str, MethodInfo] = field(default_factory=dict)
    header_pairs: List[Tuple[str, str]] = field(default_factory=list)
    main_page_pairs: List[Tuple[str, str]] = field(default_factory=list)
    constructor_strings: List[str] = field(default_factory=list)
    data_classes: Dict[str, List[str]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Ana decompile fonksiyonu
# ---------------------------------------------------------------------------

def deep_parse_cs3(data: bytes, fallback_name: str = "Unknown") -> CS3ParseResult:
    """Androguard ile CS3 dosyasini tam olarak decompile eder."""
    from androguard.core.dex import DEX

    zf = zipfile.ZipFile(io.BytesIO(data))

    manifest = _parse_manifest(zf, fallback_name)

    if "classes.dex" not in zf.namelist():
        return _empty_result(manifest)

    dex_bytes = zf.read("classes.dex")
    dex = DEX(dex_bytes)

    provider = _find_and_analyze_provider(dex, manifest)
    all_strings = _collect_all_strings(dex)
    class_names = _collect_class_names(dex)

    main_class_base = manifest.plugin_class_name.rsplit(".", 1)[-1] if manifest.plugin_class_name else ""
    if main_class_base.endswith("Plugin"):
        main_class_base = main_class_base[:-6]

    categorized = _build_categorized(provider, all_strings, manifest)
    main_url = _resolve_main_url(manifest.name, provider, categorized.urls)
    tv_types = _detect_tv_types(all_strings, provider)
    plugin_type = _detect_plugin_type(provider, categorized)
    auth_pattern, auth_details = _detect_auth(provider)

    provider_fields = {}
    for fname, fobj in provider.fields.items():
        if fobj.value is not None:
            provider_fields[fname] = fobj.value
    if provider.header_pairs:
        provider_fields["_header_pairs"] = provider.header_pairs
    if provider.main_page_pairs:
        provider_fields["_main_page_pairs"] = provider.main_page_pairs

    api_methods = []
    for mname, minfo in provider.methods.items():
        if minfo.strings or minfo.http_urls:
            api_methods.append({
                "name": mname,
                "descriptor": minfo.descriptor,
                "strings": minfo.strings,
                "http_urls": minfo.http_urls,
                "invoked_methods": minfo.invoked_methods[:20],
            })

    return CS3ParseResult(
        manifest=manifest,
        all_strings=all_strings,
        categorized=categorized,
        class_names=class_names,
        main_class_name=main_class_base or manifest.name,
        plugin_type=plugin_type,
        main_url=main_url,
        tv_types=tv_types,
        provider_fields=provider_fields,
        api_methods=api_methods,
        auth_pattern=auth_pattern,
        auth_details=auth_details,
    )


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def _parse_manifest(zf: zipfile.ZipFile, fallback_name: str) -> CS3Manifest:
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
            print(f"[CS3Decompiler] manifest.json parse hata: {e}")
    return manifest


def _empty_result(manifest: CS3Manifest) -> CS3ParseResult:
    return CS3ParseResult(
        manifest=manifest,
        all_strings=[],
        categorized=CategorizedStrings(),
        class_names=[],
    )


# ---------------------------------------------------------------------------
# Provider sinifini bul ve analiz et
# ---------------------------------------------------------------------------

def _find_and_analyze_provider(dex, manifest: CS3Manifest) -> DecompiledProvider:
    provider = DecompiledProvider()
    plugin_pkg = manifest.plugin_class_name.rsplit(".", 1)[0] if manifest.plugin_class_name else ""
    plugin_pkg_dex = "L" + plugin_pkg.replace(".", "/") + "/" if plugin_pkg else ""

    target_class_name = None

    for cls in dex.get_classes():
        cn = str(cls.get_name())
        sc = str(cls.get_superclassname())

        if "MainAPI" in sc:
            target_class_name = cn
            provider.class_name = cn
            provider.super_class = sc

            for fld in cls.get_fields():
                fname = str(fld.get_name())
                ftype = str(fld.get_descriptor())
                provider.fields[fname] = ProviderField(name=fname, type_desc=ftype)

            for method in cls.get_methods():
                mname = str(method.get_name())
                mdesc = str(method.get_descriptor())
                minfo = _analyze_method(method)
                minfo.name = mname
                minfo.descriptor = mdesc

                key = mname
                if key in provider.methods:
                    key = f"{mname}_{mdesc[:20]}"
                provider.methods[key] = minfo

                if mname == "<init>" and minfo.strings:
                    provider.constructor_strings = minfo.strings
                    _extract_pairs_from_constructor(minfo, provider)
            break

    if plugin_pkg_dex:
        for cls in dex.get_classes():
            cn = str(cls.get_name())
            if cn.startswith(plugin_pkg_dex) and cn != target_class_name:
                if "$" in cn and cn.split("$")[0] + ";" == target_class_name:
                    inner_name = cn.split("$")[-1].rstrip(";")
                    if _is_data_class(cls):
                        fields = []
                        for fld in cls.get_fields():
                            fname = str(fld.get_name())
                            ftype = str(fld.get_descriptor())
                            fields.append(f"{fname}: {_jvm_type_to_python(ftype)}")
                        provider.data_classes[inner_name] = fields

    return provider


def _is_data_class(cls) -> bool:
    """Kotlin data class tespiti: copy, component1, equals, hashCode, toString metodlari varsa."""
    method_names = {str(m.get_name()) for m in cls.get_methods()}
    return "copy" in method_names and "component1" in method_names


def _jvm_type_to_python(desc: str) -> str:
    mapping = {
        "I": "int", "J": "int", "F": "float", "D": "float",
        "Z": "bool", "B": "int", "S": "int", "C": "str",
        "Ljava/lang/String;": "str",
        "Ljava/lang/Integer;": "Optional[int]",
        "Ljava/lang/Double;": "Optional[float]",
        "Ljava/lang/Boolean;": "Optional[bool]",
        "Ljava/util/List;": "List",
    }
    return mapping.get(desc, "Any")


# ---------------------------------------------------------------------------
# Method analizi
# ---------------------------------------------------------------------------

def _analyze_method(method) -> MethodInfo:
    minfo = MethodInfo(name="", descriptor="")
    code = method.get_code()
    if not code:
        return minfo

    bc = code.get_bc()
    for inst in bc.get_instructions():
        op = inst.get_name()
        out = inst.get_output()

        if "const-string" in op:
            val = out.split(",", 1)[-1].strip().strip('"')
            minfo.strings.append(val)
            if val.startswith("http://") or val.startswith("https://"):
                minfo.http_urls.append(val)

        elif "invoke" in op and "->" in out:
            call_target = out.split("->")[-1].split("(")[0].strip()
            minfo.invoked_methods.append(call_target)

    return minfo


# ---------------------------------------------------------------------------
# Constructor'dan header ve mainPage pair'lerini cikar
# ---------------------------------------------------------------------------

def _extract_pairs_from_constructor(minfo: MethodInfo, provider: DecompiledProvider):
    """Constructor'daki string listesinden header key-value ve mainPage label-url cikarimi."""
    strings = minfo.strings

    header_keys = {
        "cf-control", "sec-ch-ua-platform", "user-agent", "accept",
        "sec-ch-ua", "sec-ch-ua-mobile", "sec-gpc", "accept-language",
        "origin", "sec-fetch-site", "sec-fetch-mode", "sec-fetch-dest",
        "referer", "accept-encoding", "priority", "user-profile",
        "user-session", "x-e-h", "x-api-key", "authorization",
        "cookie", "x-requested-with", "content-type",
    }

    i = 0
    in_headers = False
    in_main_page = False

    while i < len(strings):
        s = strings[i]
        s_lower = s.lower()

        if s_lower in header_keys:
            in_headers = True
            in_main_page = False
            if i + 1 < len(strings):
                provider.header_pairs.append((s, strings[i + 1]))
                i += 2
                continue
            i += 1
            continue

        if s.startswith("/page/") or s.startswith("/secure/") or s.startswith("/api/"):
            in_main_page = True
            in_headers = False
            url = s
            if i + 1 < len(strings) and not strings[i + 1].startswith("/") and not strings[i + 1].lower() in header_keys:
                label = strings[i + 1]
                provider.main_page_pairs.append((label, url))
                i += 2
                continue
            provider.main_page_pairs.append((s, s))
            i += 1
            continue

        if in_main_page and i > 0:
            prev = strings[i - 1] if i - 1 >= 0 else ""
            if prev.startswith("/"):
                pass

        i += 1


# ---------------------------------------------------------------------------
# String toplama
# ---------------------------------------------------------------------------

def _collect_all_strings(dex) -> List[str]:
    result = []
    for s in dex.get_strings():
        result.append(str(s))
    return result


def _collect_class_names(dex) -> List[str]:
    names = []
    for cls in dex.get_classes():
        cn = str(cls.get_name())
        if cn.startswith("L") and cn.endswith(";"):
            names.append(cn[1:-1].replace("/", "."))
    return names


# ---------------------------------------------------------------------------
# Categorized strings
# ---------------------------------------------------------------------------

def _build_categorized(
    provider: DecompiledProvider, all_strings: List[str], manifest: CS3Manifest
) -> CategorizedStrings:
    cat = CategorizedStrings()

    for key, val in provider.header_pairs:
        cat.headers[key] = val

    for label, url in provider.main_page_pairs:
        cat.main_page_entries.append(url)
        cat.main_page_labels.append(label)

    seen_urls: Set[str] = set()
    seen_endpoints: Set[str] = set()

    for s in all_strings:
        if not s or len(s) < 2 or len(s) > 2000:
            continue

        if s.startswith("SMAP\n") or s.startswith("~~") or s.startswith("$i$a$"):
            continue
        if s.startswith("(") and ")" in s and "L" in s:
            continue
        if any(s.startswith(p) for p in ("Lcom/", "Ljava/", "Lkotlin/", "Ldalvik/", "Lokhttp3/", "Lorg/", "Landroid/")):
            continue

        if s.startswith("https://") or s.startswith("http://"):
            if s not in seen_urls:
                seen_urls.add(s)
                cat.urls.append(s)
                for domain in KNOWN_EXTRACTORS:
                    if domain in s:
                        if domain not in cat.extractor_domains:
                            cat.extractor_domains.append(domain)
                        break
                if "api_key=" in s:
                    m = re.search(r"api_key=([a-f0-9]+)", s)
                    if m:
                        cat.api_keys["api_key"] = m.group(1)
            continue

        if s.startswith("/") and not s.startswith("//"):
            if s not in seen_endpoints:
                seen_endpoints.add(s)
                if any(k in s.lower() for k in ["search", "?adi=", "?s=", "?q="]):
                    cat.search_endpoints.append(s)
                elif s not in cat.main_page_entries:
                    cat.endpoints.append(s)
            continue

    for mname, minfo in provider.methods.items():
        if "search" in mname.lower():
            for s in minfo.strings:
                if s.startswith("/") and "search" in s.lower() and s not in cat.search_endpoints:
                    cat.search_endpoints.append(s)
                if "?q=" in s or "?adi=" in s or "?s=" in s:
                    if s not in cat.search_endpoints:
                        cat.search_endpoints.append(s)

    return cat


# ---------------------------------------------------------------------------
# mainUrl tespiti
# ---------------------------------------------------------------------------

def _resolve_main_url(
    name: str, provider: DecompiledProvider, urls: List[str]
) -> str:
    from urllib.parse import urlparse

    domain_from_list = _fetch_domain_from_list(name)
    if domain_from_list:
        return domain_from_list

    if "mainUrl" in provider.fields and provider.fields["mainUrl"].value:
        val = provider.fields["mainUrl"].value
        if val and "example" not in val:
            return val

    skip_domains = {
        "github.com", "githubusercontent.com", "google.com",
        "youtube.com", "example.com", "w3.org", "schema.org",
        "mozilla.org", "cloudflare.com", "gstatic.com",
        "googleapis.com", "recaptcha.net", "jsdelivr.net",
    }

    for url in provider.constructor_strings:
        if url.startswith("https://"):
            parsed = urlparse(url)
            if parsed.netloc and not any(d in parsed.netloc for d in skip_domains):
                return f"{parsed.scheme}://{parsed.netloc}"

    # Constructor'da bulunamadıysa tüm method URL'lerine bak
    # Öncelik: getMainPage > search > load > diğer
    priority_methods = ["getMainPage", "search", "load"]
    for target_method in priority_methods:
        for mname, minfo in provider.methods.items():
            if target_method in mname.lower():
                for url in minfo.http_urls:
                    parsed = urlparse(url)
                    if parsed.netloc and not any(d in parsed.netloc for d in skip_domains):
                        return f"{parsed.scheme}://{parsed.netloc}"

    # Son çare: DEX'teki tüm URL'ler arasından en uygununu seç
    domain_counts: Dict[str, int] = {}
    for url in urls:
        try:
            parsed = urlparse(url)
            netloc = parsed.netloc
            if netloc and not any(d in netloc for d in skip_domains):
                domain_counts[netloc] = domain_counts.get(netloc, 0) + 1
        except Exception:
            continue

    if domain_counts:
        best_domain = max(domain_counts, key=domain_counts.get)
        return f"https://{best_domain}"

    return ""


# ---------------------------------------------------------------------------
# TvType tespiti
# ---------------------------------------------------------------------------

def _detect_tv_types(all_strings: List[str], provider: DecompiledProvider) -> List[str]:
    types = set()

    for s in all_strings:
        if s.startswith("TvType.") or s.startswith("TvType$"):
            t = s.split(".", 1)[-1].split("$", 1)[-1]
            if t in TV_TYPE_MAP:
                types.add(TV_TYPE_MAP[t])
        elif s in TV_TYPE_MAP:
            types.add(TV_TYPE_MAP[s])

    if "supportedTypes" in provider.fields:
        for s in provider.constructor_strings:
            if s in TV_TYPE_MAP:
                types.add(TV_TYPE_MAP[s])

    if not types:
        types.add("TvSeries")
    return sorted(types)


# ---------------------------------------------------------------------------
# Plugin tipi tespiti
# ---------------------------------------------------------------------------

def _detect_plugin_type(provider: DecompiledProvider, cat: CategorizedStrings) -> str:
    has_api = any(
        "/page/" in e or "/api/" in e or "/secure/" in e or "/anime/" in e
        for e in cat.endpoints + cat.main_page_entries
    )
    has_selectors = False
    for minfo in provider.methods.values():
        for s in minfo.strings:
            if s.startswith("div.") or s.startswith("a.") or s.startswith("#"):
                has_selectors = True
                break

    if has_api and not has_selectors:
        return "api"
    elif has_selectors and not has_api:
        return "scraper"
    elif has_api and has_selectors:
        return "hybrid"
    return "api"


# ---------------------------------------------------------------------------
# Auth mekanizmasi tespiti
# ---------------------------------------------------------------------------

def _detect_auth(provider: DecompiledProvider) -> Tuple[str, Dict]:
    """Header pair'lerinden auth mekanizmasini tespit et."""
    details: Dict[str, Any] = {}

    auth_headers = {}
    for key, val in provider.header_pairs:
        kl = key.lower()
        if kl in ("cf-control", "x-api-key", "authorization", "x-e-h",
                   "user-session", "api-key", "token"):
            auth_headers[key] = val

    if not auth_headers:
        return "none", details

    details["headers"] = auth_headers

    has_hex_token = any(
        re.match(r"^[0-9a-f]{20,}$", v) for v in auth_headers.values()
    )
    has_bearer = any("bearer" in v.lower() for v in auth_headers.values() if v)
    has_base64 = any("==" in v for v in auth_headers.values() if v)

    if has_hex_token:
        return "static_hex_token", details
    elif has_bearer:
        return "bearer_token", details
    elif has_base64:
        return "static_base64_token", details
    else:
        return "static_token", details
