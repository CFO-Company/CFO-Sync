from __future__ import annotations

from pathlib import Path

from cfo_sync.platforms.base import PlatformConnector
from cfo_sync.platforms.meta_ads.connector import MetaAdsConnector
from cfo_sync.platforms.omie.connector import OmieConnector
from cfo_sync.platforms.omie.credentials import OMIE_CREDENTIALS_PATH, resolve_omie_credentials_path
from cfo_sync.platforms.yampi.connector import YampiConnector

try:
    from cfo_sync.platforms.mercado_livre.connector import MercadoLivreConnector
except ModuleNotFoundError:
    MercadoLivreConnector = None

try:
    from cfo_sync.platforms.tiktok_ads.connector import TikTokAdsConnector
except ModuleNotFoundError:
    TikTokAdsConnector = None


def build_platform_registry(
    yampi_credentials_path: Path,
    meta_ads_credentials_path: Path,
) -> dict[str, PlatformConnector]:
    omie_credentials_path = resolve_omie_credentials_path(OMIE_CREDENTIALS_PATH)

    registry: dict[str, PlatformConnector] = {
        "yampi": YampiConnector(credentials_path=yampi_credentials_path),
        "meta_ads": MetaAdsConnector(credentials_path=meta_ads_credentials_path),
    }

    if omie_credentials_path is not None:
        registry["omie"] = OmieConnector(credentials_path=omie_credentials_path)

    if MercadoLivreConnector is not None:
        registry["mercado_livre"] = MercadoLivreConnector()

    if TikTokAdsConnector is not None:
        registry["tiktok_ads"] = TikTokAdsConnector()

    return registry
