from __future__ import annotations

from pathlib import Path

from cfo_sync.platforms.base import PlatformConnector
from cfo_sync.platforms.bling.connector import BlingConnector
from cfo_sync.platforms.google_ads.connector import GoogleAdsConnector
from cfo_sync.platforms.meta_ads.connector import MetaAdsConnector
from cfo_sync.platforms.omie.connector import OmieConnector
from cfo_sync.platforms.yampi.connector import YampiConnector

try:
    from cfo_sync.platforms.mercado_livre.connector import MercadoLivreConnector
except ModuleNotFoundError:
    MercadoLivreConnector = None

try:
    from cfo_sync.platforms.tiktok_ads.connector import TikTokAdsConnector
except ModuleNotFoundError:
    TikTokAdsConnector = None

try:
    from cfo_sync.platforms.tiktok_shop.connector import TikTokShopConnector
except ModuleNotFoundError:
    TikTokShopConnector = None


def build_platform_registry(
    yampi_credentials_path: Path,
    meta_ads_credentials_path: Path,
    google_ads_credentials_path: Path,
    tiktok_ads_credentials_path: Path,
    tiktok_shop_credentials_path: Path,
    bling_credentials_path: Path,
    omie_2026_credentials_path: Path,
    omie_2025_credentials_path: Path,
    omie_cfo_credentials_path: Path,
    mercado_livre_credentials_path: Path,
) -> dict[str, PlatformConnector]:
    registry: dict[str, PlatformConnector] = {
        "yampi": YampiConnector(credentials_path=yampi_credentials_path),
        "meta_ads": MetaAdsConnector(credentials_path=meta_ads_credentials_path),
        "google_ads": GoogleAdsConnector(credentials_path=google_ads_credentials_path),
        "bling": BlingConnector(credentials_path=bling_credentials_path),
    }

    if omie_2026_credentials_path.exists():
        try:
            omie_2026_connector = OmieConnector(credentials_path=omie_2026_credentials_path)
            registry["omie"] = omie_2026_connector
            registry["omie_2026"] = omie_2026_connector
        except (OSError, ValueError, KeyError, TypeError):
            pass

    if omie_2025_credentials_path.exists():
        try:
            registry["omie_2025"] = OmieConnector(credentials_path=omie_2025_credentials_path)
        except (OSError, ValueError, KeyError, TypeError):
            pass

    if omie_cfo_credentials_path.exists():
        try:
            registry["omie_cfo"] = OmieConnector(credentials_path=omie_cfo_credentials_path)
        except (OSError, ValueError, KeyError, TypeError):
            pass

    if MercadoLivreConnector is not None:
        registry["mercado_livre"] = MercadoLivreConnector(
            credentials_path=mercado_livre_credentials_path
        )

    if TikTokAdsConnector is not None:
        registry["tiktok_ads"] = TikTokAdsConnector(credentials_path=tiktok_ads_credentials_path)

    if TikTokShopConnector is not None:
        registry["tiktok_shop"] = TikTokShopConnector(credentials_path=tiktok_shop_credentials_path)

    return registry
