from __future__ import annotations

from pathlib import Path

from cfo_sync.platforms.base import PlatformConnector
from cfo_sync.platforms.mercado_livre.connector import MercadoLivreConnector
from cfo_sync.platforms.meta_ads.connector import MetaAdsConnector
from cfo_sync.platforms.tiktok_ads.connector import TikTokAdsConnector
from cfo_sync.platforms.yampi.connector import YampiConnector


def build_platform_registry(
    yampi_credentials_path: Path,
    meta_ads_credentials_path: Path,
) -> dict[str, PlatformConnector]:
    return {
        "yampi": YampiConnector(credentials_path=yampi_credentials_path),
        "mercado_livre": MercadoLivreConnector(),
        "tiktok_ads": TikTokAdsConnector(),
        "meta_ads": MetaAdsConnector(credentials_path=meta_ads_credentials_path),
    }
