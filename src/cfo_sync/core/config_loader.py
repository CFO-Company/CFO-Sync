from __future__ import annotations

import json
import re
from pathlib import Path

from cfo_sync.core.models import (
    AppConfig,
    GoogleSheetsConfig,
    MetaAdsConfig,
    PlatformConfig,
    ResourceConfig,
    SheetTabTarget,
    YampiConfig,
)
from cfo_sync.platforms.omie.credentials import build_omie_platform_config


def _extract_spreadsheet_id(spreadsheet_url: str) -> str:
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", spreadsheet_url)
    if not match:
        raise ValueError(f"URL de planilha invalida: {spreadsheet_url}")
    return match.group(1)


def load_app_config(config_path: Path) -> AppConfig:
    data = json.loads(config_path.read_text(encoding="utf-8-sig"))
    app_root = _resolve_app_root(config_path)
    credentials_dir = _resolve_path(data["credentials_dir"], app_root)

    platforms: list[PlatformConfig] = []
    for platform_data in data["platforms"]:
        resources: list[ResourceConfig] = []
        for item in platform_data["resources"]:
            spreadsheet_url = item["spreadsheet_url"]
            spreadsheet_id = item.get("spreadsheet_id") or _extract_spreadsheet_id(spreadsheet_url)
            client_tabs = {
                client_name: SheetTabTarget(
                    tab_name=tab_data.get("tab_name", ""),
                    gid=str(tab_data["gid"]),
                    spreadsheet_id=tab_data.get("spreadsheet_id"),
                )
                for client_name, tab_data in item["client_tabs"].items()
            }

            resources.append(
                ResourceConfig(
                    name=item["name"],
                    endpoint=item["endpoint"],
                    spreadsheet_url=spreadsheet_url,
                    spreadsheet_id=spreadsheet_id,
                    field_map=item["field_map"],
                    client_tabs=client_tabs,
                )
            )

        platforms.append(
            PlatformConfig(
                key=platform_data["key"],
                label=platform_data["label"],
                clients=platform_data["clients"],
                resources=resources,
            )
        )

    platforms = [platform for platform in platforms if platform.key != "omie"]
    omie_platform = build_omie_platform_config(credentials_dir / "omie_credentials.json")
    if omie_platform is not None:
        platforms.append(omie_platform)

    return AppConfig(
        database_path=_resolve_path(data["database_path"], app_root),
        credentials_dir=credentials_dir,
        google_sheets=GoogleSheetsConfig(
            credentials_file=data["google_sheets"]["credentials_file"],
        ),
        yampi=YampiConfig(
            credentials_file=data["yampi"]["credentials_file"],
        ),
        meta_ads=MetaAdsConfig(
            credentials_file=data["meta_ads"]["credentials_file"],
        ),
        platforms=platforms,
    )


def _resolve_app_root(config_path: Path) -> Path:
    if config_path.parent.name.lower() == "secrets":
        return config_path.parent.parent
    return config_path.parent


def _resolve_path(raw_path: str, root: Path) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (root / path).resolve()
