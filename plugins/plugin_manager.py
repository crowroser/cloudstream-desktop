"""
PluginManager — loads, unloads and updates CloudStream Desktop plugins.
Plugins are .py files or .zip packages containing a manifest.json.
"""
from __future__ import annotations
import importlib.util
import importlib
import json
import os
import sys
import shutil
import hashlib
import zipfile
import threading
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any

from plugins.base_plugin import BasePlugin, PluginManifest

PLUGINS_DIR = Path(os.path.expanduser("~")) / ".cloudstream-desktop" / "plugins"
LOCAL_PLUGINS_DIR = Path(os.path.expanduser("~")) / "Cloudstream3" / "plugins"

PLUGINS_DIR.mkdir(parents=True, exist_ok=True)


class PluginData:
    def __init__(self, internal_name: str, url: Optional[str],
                 is_online: bool, file_path: str, version: int):
        self.internal_name = internal_name
        self.url = url
        self.is_online = is_online
        self.file_path = file_path
        self.version = version

    def to_dict(self) -> dict:
        return {
            "internal_name": self.internal_name,
            "url": self.url,
            "is_online": self.is_online,
            "file_path": self.file_path,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PluginData":
        return cls(
            internal_name=d["internal_name"],
            url=d.get("url"),
            is_online=d.get("is_online", False),
            file_path=d["file_path"],
            version=d.get("version", 0),
        )


class _PluginManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._plugins: Dict[str, BasePlugin] = {}
        self._plugin_data: Dict[str, PluginData] = {}
        self._after_load_callbacks: List[Callable] = []
        self._prefs_path = (
            Path(os.path.expanduser("~")) / ".cloudstream-desktop" / "plugins_registry.json"
        )
        self._registry_dirty = False
        self._registry_timer: Optional[threading.Timer] = None
        self._load_registry()

    # ------------------------------------------------------------------
    # Registry persistence
    # ------------------------------------------------------------------

    def _load_registry(self) -> None:
        if self._prefs_path.exists():
            try:
                data = json.loads(self._prefs_path.read_text("utf-8"))
                for key, val in data.items():
                    self._plugin_data[key] = PluginData.from_dict(val)
            except Exception as e:
                print(f"[PluginManager] Registry load error: {e}")

    def _save_registry(self) -> None:
        try:
            self._prefs_path.parent.mkdir(parents=True, exist_ok=True)
            data = {k: v.to_dict() for k, v in self._plugin_data.items()}
            self._prefs_path.write_text(json.dumps(data, indent=2), "utf-8")
            self._registry_dirty = False
        except Exception as e:
            print(f"[PluginManager] Registry save error: {e}")

    def _save_registry_debounced(self) -> None:
        """Toplu islemlerde disk I/O'yu azaltmak icin 2sn gecikmeyle kaydeder."""
        self._registry_dirty = True
        if self._registry_timer is not None:
            self._registry_timer.cancel()
        self._registry_timer = threading.Timer(2.0, self._flush_registry)
        self._registry_timer.daemon = True
        self._registry_timer.start()

    def _flush_registry(self) -> None:
        if self._registry_dirty:
            self._save_registry()

    # ------------------------------------------------------------------
    # Load a single plugin
    # ------------------------------------------------------------------

    def load_plugin(
        self, file_path: str,
        plugin_data: Optional[PluginData] = None,
        save_to_registry: bool = True,
    ) -> bool:
        """Load a plugin from a .py or .zip file."""
        path = Path(file_path)
        if not path.exists():
            print(f"[PluginManager] File not found: {file_path}")
            return False

        with self._lock:
            if file_path in self._plugins:
                return True  # zaten yuklenmis

        try:
            manifest, plugin_py_path = self._extract_plugin(path)
        except Exception as e:
            print(f"[PluginManager] Failed to extract {file_path}: {e}")
            return False

        try:
            plugin_instance = self._instantiate_plugin(plugin_py_path, manifest)
        except Exception as e:
            print(f"[PluginManager] Failed to instantiate {manifest.plugin_class_name}: {e}")
            return False

        plugin_instance.filename = str(path)
        plugin_instance.manifest = manifest

        with self._lock:
            self._plugins[file_path] = plugin_instance

        if save_to_registry and plugin_data:
            self._plugin_data[file_path] = plugin_data
            self._save_registry_debounced()

        try:
            plugin_instance.load()
            print(f"[PluginManager] Loaded: {manifest.name} v{manifest.version}")
        except Exception as e:
            print(f"[PluginManager] Plugin.load() error [{manifest.name}]: {e}")
            return False

        return True

    def _extract_plugin(self, path: Path):
        """Read manifest.json and return (manifest, path_to_plugin.py)."""
        if path.suffix == ".zip":
            extract_dir = PLUGINS_DIR / "extracted" / path.stem
            extract_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(path, "r") as zf:
                zf.extractall(extract_dir)
            manifest_path = extract_dir / "manifest.json"
            plugin_py = extract_dir / "plugin.py"
        elif path.suffix == ".py":
            manifest_path = path.parent / "manifest.json"
            plugin_py = path
        else:
            raise ValueError(f"Unsupported plugin format: {path.suffix}")

        manifest = PluginManifest(
            name=path.stem,
            plugin_class_name="Plugin",
            version=0,
        )
        if manifest_path.exists():
            data = json.loads(manifest_path.read_text("utf-8"))
            manifest = PluginManifest(
                name=data.get("name", path.stem),
                plugin_class_name=data.get("plugin_class_name", "Plugin"),
                version=data.get("version", 0),
                internal_name=data.get("internal_name", path.stem),
                description=data.get("description", ""),
                author=data.get("author", ""),
                language=data.get("language", "en"),
                tv_types=data.get("tv_types", []),
                icon_url=data.get("icon_url"),
            )
        return manifest, plugin_py

    def _instantiate_plugin(self, plugin_py: Path, manifest: PluginManifest) -> BasePlugin:
        """Dynamically load a Python file and instantiate the plugin class."""
        module_name = f"_plugin_{hashlib.md5(str(plugin_py).encode()).hexdigest()[:8]}"
        spec = importlib.util.spec_from_file_location(module_name, str(plugin_py))
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        cls_name = manifest.plugin_class_name
        if not hasattr(module, cls_name):
            # Try to find any BasePlugin subclass
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                try:
                    if (isinstance(attr, type) and issubclass(attr, BasePlugin)
                            and attr is not BasePlugin):
                        return attr()
                except TypeError:
                    pass
            raise AttributeError(f"Class '{cls_name}' not found in {plugin_py}")

        return getattr(module, cls_name)()

    # ------------------------------------------------------------------
    # Unload
    # ------------------------------------------------------------------

    def unload_plugin(self, file_path: str) -> None:
        with self._lock:
            self._do_unload(file_path)
        self._save_registry()

    def _do_unload(self, file_path: str) -> None:
        plugin = self._plugins.pop(file_path, None)
        if plugin is None:
            return
        try:
            plugin.before_unload()
        except Exception as e:
            print(f"[PluginManager] before_unload error: {e}")

        from core.api_holder import APIHolder
        APIHolder.remove_plugin_apis(file_path)
        APIHolder.remove_plugin_extractors(file_path)
        self._plugin_data.pop(file_path, None)
        print(f"[PluginManager] Unloaded: {file_path}")

    # ------------------------------------------------------------------
    # Bulk operations
    # ------------------------------------------------------------------

    def load_all_registered_plugins(self) -> None:
        """Load all plugins stored in the registry. CS3 dosyalarini otomatik donusturur."""
        # Eksik dosyalari ve .py duplicate'lerini temizle
        self._clean_registry()

        for file_path, pdata in list(self._plugin_data.items()):
            path = Path(file_path)
            if not path.exists():
                continue

            if path.suffix == ".cs3":
                self._convert_and_load_cs3(path, pdata)
            elif path.suffix in (".py", ".zip"):
                self.load_plugin(file_path, pdata)
        self._notify_loaded()

    def _clean_registry(self) -> None:
        """Eksik dosyalari ve duplicate kayitlari temizle."""
        to_remove = []
        seen_names = set()
        for fp, pd in list(self._plugin_data.items()):
            path = Path(fp)
            # .py dosyasi .cs3 ile ayni ada sahipse, .py kaydini sil (cs3 key yeterli)
            if path.suffix == ".py" and path.with_suffix(".cs3").exists():
                cs3_key = str(path.with_suffix(".cs3"))
                if cs3_key in self._plugin_data:
                    to_remove.append(fp)
                    continue
            # Dosya yoksa sil
            if not path.exists():
                to_remove.append(fp)
                continue
            # Ayni internal_name'den birden fazla kayit varsa, ilkini tut
            if pd.internal_name in seen_names:
                to_remove.append(fp)
                continue
            seen_names.add(pd.internal_name)

        if to_remove:
            for fp in to_remove:
                self._plugin_data.pop(fp, None)
                print(f"[PluginManager] Registry temizlendi: {Path(fp).name}")
            self._save_registry()

    def _convert_and_load_cs3(self, cs3_path: Path, pdata: PluginData) -> None:
        """CS3 dosyasini Python'a cevirip yukler."""
        from plugins.cs3_to_python import CS3_GEN_VERSION
        py_path = cs3_path.with_suffix(".py")
        needs_regen = not py_path.exists()
        if not needs_regen:
            try:
                first_line = py_path.read_text(encoding="utf-8", errors="ignore")[:50]
                if f"CS3_GEN_V{CS3_GEN_VERSION}" not in first_line:
                    needs_regen = True
            except Exception:
                pass
        if needs_regen:
            try:
                from plugins.cs3_parser import parse_cs3
                from plugins.cs3_to_python import generate_plugin

                parsed = parse_cs3(str(cs3_path))
                py_code = generate_plugin(parsed)
                py_path.write_text(py_code, encoding="utf-8")
                print(f"[PluginManager] CS3 -> Python: {cs3_path.stem}")
            except Exception as e:
                print(f"[PluginManager] CS3 donusum hatasi [{cs3_path.stem}]: {e}")
                return

        self.load_plugin(str(py_path), save_to_registry=False)

    def load_all_local_plugins(self) -> None:
        """Load .py files from the local user plugins directory."""
        if not LOCAL_PLUGINS_DIR.exists():
            return
        for py_file in LOCAL_PLUGINS_DIR.glob("*.py"):
            dest = PLUGINS_DIR / py_file.name
            shutil.copy2(py_file, dest)
            pdata = PluginData(
                internal_name=py_file.stem,
                url=None,
                is_online=False,
                file_path=str(dest),
                version=0,
            )
            self.load_plugin(str(dest), pdata)
        self._notify_loaded()

    def reload_all_local_plugins(self) -> None:
        local = [fp for fp, pd in self._plugin_data.items() if not pd.is_online]
        for fp in local:
            self.unload_plugin(fp)
        self.load_all_local_plugins()

    def _notify_loaded(self) -> None:
        from core.api_holder import APIHolder
        APIHolder.notify_plugins_loaded()
        for cb in self._after_load_callbacks:
            try:
                cb()
            except Exception as e:
                print(f"[PluginManager] Callback error: {e}")

    def on_after_plugins_loaded(self, callback: Callable) -> None:
        self._after_load_callbacks.append(callback)

    # ------------------------------------------------------------------
    # Install / Delete
    # ------------------------------------------------------------------

    def install_plugin_from_file(self, src_path: str) -> bool:
        """Copy a plugin file to the plugins dir and load it."""
        src = Path(src_path)
        dest = PLUGINS_DIR / src.name
        shutil.copy2(src, dest)
        pdata = PluginData(
            internal_name=src.stem,
            url=None,
            is_online=False,
            file_path=str(dest),
            version=0,
        )
        return self.load_plugin(str(dest), pdata)

    def delete_plugin(self, file_path: str) -> None:
        path = Path(file_path)
        # CS3 dosyasi ise, uretilmis .py dosyasini da temizle
        py_path = path.with_suffix(".py")
        if path.suffix == ".cs3" and py_path.exists():
            sp = str(py_path)
            if sp in self._plugins:
                with self._lock:
                    self._do_unload(sp)
            try:
                py_path.unlink(missing_ok=True)
            except Exception:
                pass
        self.unload_plugin(file_path)
        try:
            path.unlink(missing_ok=True)
        except Exception as e:
            print(f"[PluginManager] Delete error: {e}")

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_loaded_plugins(self) -> Dict[str, BasePlugin]:
        return dict(self._plugins)

    def get_plugin_data(self) -> Dict[str, PluginData]:
        return dict(self._plugin_data)

    def is_loaded(self, file_path: str) -> bool:
        return file_path in self._plugins

    def get_plugin_path(self, repo_url: str, internal_name: str) -> Path:
        repo_hash = hashlib.md5(repo_url.encode()).hexdigest()[:8]
        name_hash = hashlib.md5(internal_name.encode()).hexdigest()[:8]
        return PLUGINS_DIR / repo_hash / f"{name_hash}.py"


PluginManager = _PluginManager()
