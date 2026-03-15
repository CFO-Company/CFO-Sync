from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class GoogleSheetsConfig:
    credentials_file: str


@dataclass(frozen=True)
class YampiConfig:
    credentials_file: str


@dataclass(frozen=True)
class MetaAdsConfig:
    credentials_file: str


@dataclass(frozen=True)
class GoogleAdsConfig:
    credentials_file: str


@dataclass(frozen=True)
class SheetTabTarget:
    gid: str
    tab_name: str = ""
    spreadsheet_id: str | None = None


@dataclass(frozen=True)
class ResourceConfig:
    name: str
    endpoint: str
    spreadsheet_url: str
    spreadsheet_id: str
    field_map: dict[str, str]
    client_tabs: dict[str, SheetTabTarget]


@dataclass(frozen=True)
class PlatformConfig:
    key: str
    label: str
    clients: list[str]
    resources: list[ResourceConfig]


@dataclass(frozen=True)
class AppConfig:
    database_path: Path
    credentials_dir: Path
    google_sheets: GoogleSheetsConfig
    yampi: YampiConfig
    meta_ads: MetaAdsConfig
    google_ads: GoogleAdsConfig
    platforms: list[PlatformConfig]


RawRecord = dict[str, Any]
