from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import gettempdir
from urllib.request import Request, urlopen

from cfo_sync.core.runtime_paths import update_config_path
from cfo_sync.version import __version__


GITHUB_API_BASE = "https://api.github.com"
USER_AGENT = "CFO-Sync-Updater/1.0"


@dataclass(frozen=True)
class UpdateSettings:
    enabled: bool
    github_repo: str
    windows_asset_name: str
    macos_asset_name: str


@dataclass(frozen=True)
class UpdateCheckResult:
    status: str
    message: str
    current_version: str
    latest_version: str | None = None
    release_url: str | None = None
    asset_name: str | None = None
    asset_url: str | None = None

    @property
    def update_available(self) -> bool:
        return self.status == "update_available"


def load_update_settings(path: Path | None = None) -> UpdateSettings:
    config_path = path or update_config_path()
    if not config_path.exists():
        return UpdateSettings(
            enabled=False,
            github_repo="",
            windows_asset_name="CFO-Sync-Setup.exe",
            macos_asset_name="CFO-Sync-macOS.dmg",
        )

    data = json.loads(config_path.read_text(encoding="utf-8-sig"))
    return UpdateSettings(
        enabled=bool(data.get("enabled", True)),
        github_repo=str(data.get("github_repo") or "").strip(),
        windows_asset_name=str(data.get("windows_asset_name") or "CFO-Sync-Setup.exe").strip(),
        macos_asset_name=str(data.get("macos_asset_name") or "CFO-Sync-macOS.dmg").strip(),
    )


def get_releases_page_url(path: Path | None = None) -> str | None:
    settings = load_update_settings(path)
    repo = settings.github_repo
    if not _is_valid_repo(repo):
        return None
    return f"https://github.com/{repo}/releases"


def check_for_updates(path: Path | None = None) -> UpdateCheckResult:
    settings = load_update_settings(path)
    current_version = __version__

    if not settings.enabled:
        return UpdateCheckResult(
            status="disabled",
            message="Atualizacao automatica desativada em update_config.json.",
            current_version=current_version,
        )

    repo = settings.github_repo
    if not _is_valid_repo(repo):
        return UpdateCheckResult(
            status="misconfigured",
            message=(
                "Configure o repositorio GitHub em settings/update_config.json "
                "(campo github_repo no formato owner/repo)."
            ),
            current_version=current_version,
        )

    try:
        release = _fetch_latest_release(repo)
    except Exception as error:  # noqa: BLE001
        return UpdateCheckResult(
            status="error",
            message=f"Falha ao consultar release no GitHub: {error}",
            current_version=current_version,
        )

    latest_version = _normalize_version_tag(str(release.get("tag_name") or release.get("name") or ""))
    if not latest_version:
        return UpdateCheckResult(
            status="error",
            message="Release sem versao valida (tag_name).",
            current_version=current_version,
        )

    if not _is_newer_version(latest_version, current_version):
        return UpdateCheckResult(
            status="up_to_date",
            message=f"Aplicativo ja esta na versao mais recente ({current_version}).",
            current_version=current_version,
            latest_version=latest_version,
            release_url=str(release.get("html_url") or ""),
        )

    assets = release.get("assets") or []
    selected_asset = _select_asset_for_platform(assets, settings)
    if selected_asset is None:
        return UpdateCheckResult(
            status="no_asset",
            message="Nenhum asset compativel encontrado na release mais recente.",
            current_version=current_version,
            latest_version=latest_version,
            release_url=str(release.get("html_url") or ""),
        )

    return UpdateCheckResult(
        status="update_available",
        message=f"Nova versao disponivel: {latest_version}",
        current_version=current_version,
        latest_version=latest_version,
        release_url=str(release.get("html_url") or ""),
        asset_name=str(selected_asset.get("name") or ""),
        asset_url=str(selected_asset.get("browser_download_url") or ""),
    )


def download_and_launch_update(path: Path | None = None) -> UpdateCheckResult:
    check = check_for_updates(path)
    if not check.update_available:
        return check

    if not check.asset_url or not check.asset_name:
        return UpdateCheckResult(
            status="error",
            message="Asset de atualizacao invalido.",
            current_version=check.current_version,
            latest_version=check.latest_version,
            release_url=check.release_url,
        )

    target = _download_asset(check.asset_url, check.asset_name)
    _launch_installer(target)
    return UpdateCheckResult(
        status="installer_started",
        message=f"Atualizador iniciado: {target.name}",
        current_version=check.current_version,
        latest_version=check.latest_version,
        release_url=check.release_url,
        asset_name=check.asset_name,
        asset_url=check.asset_url,
    )


def _is_valid_repo(value: str) -> bool:
    if not value or value.upper() == "OWNER/REPO":
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value))


def _fetch_latest_release(repo: str) -> dict[str, object]:
    url = f"{GITHUB_API_BASE}/repos/{repo}/releases/latest"
    request = Request(
        url=url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _normalize_version_tag(value: str) -> str:
    text = value.strip()
    if text.lower().startswith("v"):
        text = text[1:]
    return text


def _version_key(value: str) -> tuple[int, int, int]:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        return (0, 0, 0)
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _is_newer_version(latest: str, current: str) -> bool:
    return _version_key(latest) > _version_key(current)


def _select_asset_for_platform(assets: list[object], settings: UpdateSettings) -> dict[str, object] | None:
    normalized_assets: list[dict[str, object]] = [item for item in assets if isinstance(item, dict)]
    target_name = settings.windows_asset_name if sys.platform == "win32" else settings.macos_asset_name
    for asset in normalized_assets:
        name = str(asset.get("name") or "").strip()
        if name == target_name:
            return asset

    if sys.platform == "win32":
        return _first_match(normalized_assets, (".exe",), ("setup", "windows", "win"))
    if sys.platform == "darwin":
        return _first_match(normalized_assets, (".dmg", ".pkg", ".zip"), ("macos", "mac", "darwin"))
    return None


def _first_match(
    assets: list[dict[str, object]],
    extensions: tuple[str, ...],
    keywords: tuple[str, ...],
) -> dict[str, object] | None:
    scored: list[tuple[int, dict[str, object]]] = []
    for asset in assets:
        name = str(asset.get("name") or "").strip()
        lowered = name.lower()
        if not any(lowered.endswith(ext) for ext in extensions):
            continue
        score = 0
        for keyword in keywords:
            if keyword in lowered:
                score += 1
        scored.append((score, asset))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def _download_asset(asset_url: str, asset_name: str) -> Path:
    target_dir = Path(gettempdir()) / "cfo-sync-updates"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / asset_name

    request = Request(
        url=asset_url,
        headers={"User-Agent": USER_AGENT},
    )
    with urlopen(request, timeout=300) as response, target_path.open("wb") as output:
        shutil.copyfileobj(response, output)
    return target_path


def _launch_installer(installer_path: Path) -> None:
    if sys.platform == "win32":
        name = installer_path.name.lower()
        is_setup_like = "setup" in name or "installer" in name
        command = [str(installer_path)]
        if is_setup_like:
            command.extend(
                [
                    "/VERYSILENT",
                    "/SUPPRESSMSGBOXES",
                    "/NORESTART",
                ]
            )
        subprocess.Popen(
            command,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        return

    if sys.platform == "darwin":
        subprocess.Popen(["open", str(installer_path)])
        return

    raise RuntimeError("Atualizacao automatica nao suportada neste sistema operacional.")
