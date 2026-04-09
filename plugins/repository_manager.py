"""
RepositoryManager — fetches CloudStream-compatible extension repository manifests
and manages the list of available/installed plugins.
"""
from __future__ import annotations
import asyncio
import json
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Tuple
import os

from plugins.plugin_manager import PluginManager, PluginData, PLUGINS_DIR

REPOS_FILE = Path(os.path.expanduser("~")) / ".cloudstream-desktop" / "repositories.json"

# Built-in repositories
PREBUILT_REPOSITORIES: List[str] = [
    "https://raw.githubusercontent.com/Kraptor123/cs-kraptor/refs/heads/master/repo.json",
]

_CLOUDSTREAM_SCHEME = "cloudstreamrepo://"


def normalize_repo_url(url: str) -> str:
    """cloudstreamrepo:// protokolünü https:// ile değiştirir."""
    url = url.strip().rstrip("/")
    if url.startswith(_CLOUDSTREAM_SCHEME):
        url = "https://" + url[len(_CLOUDSTREAM_SCHEME):]
    return url


@dataclass
class SitePlugin:
    """Metadata for a single plugin available in a repository."""
    url: str
    name: str
    internal_name: str
    version: int
    description: str = ""
    author: str = ""
    language: str = "en"
    tv_types: List[str] = field(default_factory=list)
    icon_url: Optional[str] = None
    status: int = 1  # 1 = working
    repo_url: str = ""

    @classmethod
    def from_dict(cls, d: dict, repo_url: str = "") -> "SitePlugin":
        # authors alanı hem [{"name": "..."}] hem de ["string", ...] formatında gelebilir
        authors_raw = d.get("authors", [])
        if authors_raw:
            first = authors_raw[0]
            if isinstance(first, dict):
                author = first.get("name", "")
            else:
                author = str(first)
        else:
            author = d.get("author", "")

        return cls(
            url=d.get("url", ""),
            name=d.get("name", d.get("internalName", "Unknown")),
            internal_name=d.get("internalName", d.get("internal_name", "")),
            version=d.get("version", 0),
            description=d.get("description", ""),
            author=author,
            language=d.get("language", "en"),
            tv_types=d.get("tvTypes", d.get("tv_types", [])),
            icon_url=d.get("iconUrl", d.get("icon_url")),
            status=d.get("status", 1),
            repo_url=repo_url,
        )


@dataclass
class Repository:
    url: str
    name: str = ""
    plugin_lists: List[str] = field(default_factory=list)


class _RepositoryManager:
    def __init__(self):
        self._repos: List[str] = list(PREBUILT_REPOSITORIES)
        self._load_repos()

    # ------------------------------------------------------------------
    # Repository persistence
    # ------------------------------------------------------------------

    def _load_repos(self) -> None:
        if REPOS_FILE.exists():
            try:
                data = json.loads(REPOS_FILE.read_text("utf-8"))
                saved = data.get("repos", [])
                for r in saved:
                    if r not in self._repos:
                        self._repos.append(r)
            except Exception as e:
                print(f"[RepositoryManager] Load error: {e}")

    def _save_repos(self) -> None:
        try:
            REPOS_FILE.parent.mkdir(parents=True, exist_ok=True)
            REPOS_FILE.write_text(json.dumps({"repos": self._repos}, indent=2), "utf-8")
        except Exception as e:
            print(f"[RepositoryManager] Save error: {e}")

    def add_repository(self, url: str) -> bool:
        url = normalize_repo_url(url)
        if url not in self._repos:
            self._repos.append(url)
            self._save_repos()
            return True
        return False

    def remove_repository(self, url: str) -> None:
        if url in self._repos:
            self._repos.remove(url)
            self._save_repos()
            # Unload plugins from this repo
            for fp, pd in list(PluginManager.get_plugin_data().items()):
                if pd.url and url in pd.url:
                    PluginManager.delete_plugin(fp)

    def get_repositories(self) -> List[str]:
        return list(self._repos)

    # ------------------------------------------------------------------
    # Fetch plugin listings
    # ------------------------------------------------------------------

    async def get_repo_plugins(
        self, repo_url: str
    ) -> List[Tuple[str, SitePlugin]]:
        """
        Fetch the repository manifest and return a flat list of (repo_url, SitePlugin).
        Compatible with CloudStream's repository JSON format.
        """
        from core.utils import http_helper as http
        plugins: List[Tuple[str, SitePlugin]] = []

        try:
            raw = await http.get_json(repo_url)
        except Exception as e:
            print(f"[RepositoryManager] Failed to fetch repo {repo_url}: {e}")
            return plugins

        # CloudStream repo format: {"pluginLists": ["url1", "url2"]}
        # or flat list: [{"name": ..., "url": ...}, ...]
        if isinstance(raw, dict):
            plugin_lists = raw.get("pluginLists", [])
        elif isinstance(raw, list):
            # Direct plugin list — skip non-dict entries
            for item in raw:
                if isinstance(item, dict):
                    plugins.append((repo_url, SitePlugin.from_dict(item, repo_url)))
            return plugins
        else:
            return plugins

        for list_url in plugin_lists:
            try:
                items = await http.get_json(list_url)
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            plugins.append((repo_url, SitePlugin.from_dict(item, repo_url)))
                        # else: string URL veya bilinmeyen format, atla
                elif isinstance(items, dict):
                    # Bazı repolar tek bir plugin dict döndürebilir
                    plugins.append((repo_url, SitePlugin.from_dict(items, repo_url)))
            except Exception as e:
                print(f"[RepositoryManager] Failed to fetch plugin list {list_url}: {e}")

        return plugins

    async def get_all_plugins(self) -> List[Tuple[str, SitePlugin]]:
        """Fetch plugins from all registered repositories."""
        all_plugins: List[Tuple[str, SitePlugin]] = []
        tasks = [self.get_repo_plugins(url) for url in self._repos]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, list):
                all_plugins.extend(result)
        return all_plugins

    # ------------------------------------------------------------------
    # Download and install
    # ------------------------------------------------------------------

    def download_plugin_sync(
        self, site_plugin: SitePlugin,
        progress_callback=None
    ) -> bool:
        """
        Eklentiyi indir ve kayıt et (senkron).
        .py/.zip → Python olarak yükle.
        .cs3 → DEX parse et, Python'a cevir, yukle.
        """
        import httpx
        from pathlib import Path as _Path

        plugin_url = site_plugin.url
        url_path = _Path(plugin_url.split("?")[0])
        ext = url_path.suffix.lower() or ".cs3"

        dest = self._get_dest_path(site_plugin, ext)
        dest.parent.mkdir(parents=True, exist_ok=True)

        try:
            with httpx.Client(follow_redirects=True, timeout=60) as client:
                resp = client.get(
                    plugin_url,
                    headers={"User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/122.0.0.0 Safari/537.36"
                    )},
                )
                resp.raise_for_status()
                dest.write_bytes(resp.content)
        except Exception as e:
            print(f"[RepositoryManager] Download failed [{site_plugin.name}]: {e}")
            return False

        pdata = PluginData(
            internal_name=site_plugin.internal_name,
            url=plugin_url,
            is_online=True,
            file_path=str(dest),
            version=site_plugin.version,
        )

        if ext in (".py", ".zip"):
            return PluginManager.load_plugin(str(dest), pdata)

        if ext == ".cs3":
            return self._convert_and_load_cs3(dest, pdata, site_plugin.name)

        PluginManager._plugin_data[str(dest)] = pdata
        PluginManager._save_registry()
        return True

    def _convert_and_load_cs3(
        self, cs3_path: Path, pdata: PluginData, plugin_name: str
    ) -> bool:
        """CS3 dosyasini parse et, Python'a cevir ve plugin olarak yukle."""
        py_path = cs3_path.with_suffix(".py")
        try:
            from plugins.cs3_parser import parse_cs3
            from plugins.cs3_to_python import generate_plugin

            parsed = parse_cs3(str(cs3_path))
            py_code = generate_plugin(parsed)
            py_path.write_text(py_code, encoding="utf-8")
            print(f"[RepositoryManager] CS3 -> Python: {plugin_name} ({py_path.name})")
        except Exception as e:
            print(f"[RepositoryManager] CS3 donusum hatasi [{plugin_name}]: {e}")
            PluginManager._plugin_data[str(cs3_path)] = pdata
            PluginManager._save_registry_debounced()
            return True

        py_pdata = PluginData(
            internal_name=pdata.internal_name,
            url=pdata.url,
            is_online=True,
            file_path=str(py_path),
            version=pdata.version,
        )
        # Registry'de sadece .cs3 key'ini tut (cift kayit onle)
        PluginManager._plugin_data[str(cs3_path)] = pdata
        PluginManager._save_registry_debounced()
        return PluginManager.load_plugin(str(py_path), py_pdata, save_to_registry=False)

    async def download_plugin(
        self, site_plugin: SitePlugin,
        progress_callback=None
    ) -> bool:
        """Async wrapper (geriye dönük uyumluluk için)."""
        return self.download_plugin_sync(site_plugin, progress_callback)

    def update_plugin_sync(self, site_plugin: SitePlugin) -> bool:
        """Eklentiyi güncelle (senkron)."""
        from pathlib import Path as _Path
        url_path = _Path(site_plugin.url.split("?")[0])
        ext = url_path.suffix.lower() or ".cs3"
        dest = self._get_dest_path(site_plugin, ext)
        py_path = dest.with_suffix(".py")
        # Eski .py ve .cs3 dosyalarini unload et ve sil
        for p in [py_path, dest]:
            sp = str(p)
            if sp in PluginManager._plugins:
                PluginManager.unload_plugin(sp)
            p.unlink(missing_ok=True)
        return self.download_plugin_sync(site_plugin)

    async def update_plugin(self, site_plugin: SitePlugin) -> bool:
        """Async wrapper (geriye dönük uyumluluk için)."""
        return self.update_plugin_sync(site_plugin)

    def _get_dest_path(self, site_plugin: SitePlugin, ext: str) -> "Path":
        import hashlib
        repo_hash = hashlib.md5(site_plugin.repo_url.encode()).hexdigest()[:8]
        return PLUGINS_DIR / repo_hash / f"{site_plugin.internal_name}{ext}"

    def get_installed_version(self, internal_name: str) -> Optional[int]:
        for fp, pd in PluginManager.get_plugin_data().items():
            if pd.internal_name == internal_name:
                return pd.version
        return None

    def is_installed(self, internal_name: str) -> bool:
        return self.get_installed_version(internal_name) is not None


RepositoryManager = _RepositoryManager()
