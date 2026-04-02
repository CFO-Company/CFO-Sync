from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path


APP_DIR_NAME = "CFO-Sync"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def install_root() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def bundle_root() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass).resolve()
    return install_root()


def runtime_root() -> Path:
    override = os.getenv("CFO_SYNC_HOME")
    if override:
        return Path(override).expanduser().resolve()

    if not is_frozen():
        return install_root()

    if sys.platform == "win32":
        local_app_data = os.getenv("LOCALAPPDATA")
        if local_app_data:
            base_dir = Path(local_app_data)
        else:
            base_dir = Path.home() / "AppData" / "Local"
        return (base_dir / APP_DIR_NAME).resolve()

    if sys.platform == "darwin":
        return (Path.home() / "Library" / "Application Support" / APP_DIR_NAME).resolve()

    return (Path.home() / ".local" / "share" / APP_DIR_NAME).resolve()


def data_dir() -> Path:
    return runtime_root() / "data"


def settings_dir() -> Path:
    return runtime_root() / "settings"


def secrets_dir() -> Path:
    return runtime_root() / "secrets"


def custom_sounds_dir() -> Path:
    return runtime_root() / "sounds"


def bundled_sounds_dir() -> Path:
    return bundle_root() / "sounds"


def app_config_path() -> Path:
    return secrets_dir() / "app_config.json"


def desktop_settings_path() -> Path:
    return settings_dir() / "desktop_settings.json"


def default_omie_credentials_path() -> Path:
    return secrets_dir() / "omie_credentials.json"


def default_mercado_livre_credentials_path() -> Path:
    return secrets_dir() / "mercado_livre_credentials.json"


def update_config_path() -> Path:
    return settings_dir() / "update_config.json"


def available_sound_dirs() -> list[Path]:
    ordered: list[Path] = [custom_sounds_dir(), bundled_sounds_dir()]
    deduped: list[Path] = []
    seen: set[Path] = set()
    for item in ordered:
        resolved = item.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(resolved)
    return deduped


def ensure_runtime_layout() -> None:
    runtime_root().mkdir(parents=True, exist_ok=True)
    data_dir().mkdir(parents=True, exist_ok=True)
    settings_dir().mkdir(parents=True, exist_ok=True)
    custom_sounds_dir().mkdir(parents=True, exist_ok=True)
    _seed_update_config_template()
    _seed_desktop_settings()

def _seed_update_config_template() -> None:
    template_path = bundle_root() / "templates" / "secrets" / "update_config.json"
    target = update_config_path()
    if target.exists():
        return
    if template_path.exists():
        shutil.copyfile(template_path, target)
        return
    default_payload = {
        "enabled": False,
        "github_repo": "OWNER/REPO",
        "windows_asset_name": "CFO-Sync-Setup.exe",
        "macos_asset_name": "CFO-Sync-macOS.dmg",
    }
    target.write_text(json.dumps(default_payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _seed_desktop_settings() -> None:
    settings_path = desktop_settings_path()
    if settings_path.exists():
        return
    legacy = secrets_dir() / "desktop_settings.json"
    if legacy.exists():
        shutil.copyfile(legacy, settings_path)
        return
    settings_path.write_text("{}\n", encoding="utf-8")
