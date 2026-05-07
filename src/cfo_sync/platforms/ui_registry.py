from __future__ import annotations

from cfo_sync.core.models import AppConfig
from cfo_sync.platforms.bling.ui_behavior import BlingUIBehavior
from cfo_sync.platforms.google_ads.ui_behavior import GoogleAdsUIBehavior
from cfo_sync.platforms.mercado_livre.ui_behavior import MercadoLivreUIBehavior
from cfo_sync.platforms.meta_ads.ui_behavior import MetaAdsUIBehavior
from cfo_sync.platforms.omie.ui_behavior import OmieUIBehavior
from cfo_sync.platforms.tiktok_ads.ui_behavior import TikTokAdsUIBehavior
from cfo_sync.platforms.tiktok_shop.ui_behavior import TikTokShopUIBehavior
from cfo_sync.platforms.ui_behavior import PlatformUIBehavior
from cfo_sync.platforms.yampi.ui_behavior import YampiUIBehavior


def build_platform_ui_registry(config: AppConfig) -> dict[str, PlatformUIBehavior]:
    omie_2026_credentials_path = config.credentials_dir / "omie_credentials.json"
    omie_2025_credentials_path = config.credentials_dir / "omie_2025.json"
    omie_cfo_credentials_path = config.credentials_dir / "omie_cfo.json"
    configured_platform_keys = {platform.key for platform in config.platforms}

    registry: dict[str, PlatformUIBehavior] = {}

    if "yampi" in configured_platform_keys:
        try:
            registry["yampi"] = YampiUIBehavior(
                credentials_path=config.credentials_dir / config.yampi.credentials_file,
            )
        except (OSError, ValueError, KeyError, TypeError):
            pass

    if "meta_ads" in configured_platform_keys:
        try:
            registry["meta_ads"] = MetaAdsUIBehavior(
                credentials_path=config.credentials_dir / config.meta_ads.credentials_file,
            )
        except (OSError, ValueError, KeyError, TypeError):
            pass

    if "google_ads" in configured_platform_keys:
        try:
            registry["google_ads"] = GoogleAdsUIBehavior(
                credentials_path=config.credentials_dir / config.google_ads.credentials_file,
            )
        except (OSError, ValueError, KeyError, TypeError):
            pass

    if "mercado_livre" in configured_platform_keys:
        try:
            registry["mercado_livre"] = MercadoLivreUIBehavior(
                credentials_path=config.credentials_dir / "mercado_livre_credentials.json",
            )
        except (OSError, ValueError, KeyError, TypeError):
            pass

    if "tiktok_ads" in configured_platform_keys:
        try:
            registry["tiktok_ads"] = TikTokAdsUIBehavior(
                credentials_path=config.credentials_dir / config.tiktok_ads.credentials_file,
            )
        except (OSError, ValueError, KeyError, TypeError):
            pass

    if "tiktok_shop" in configured_platform_keys:
        try:
            registry["tiktok_shop"] = TikTokShopUIBehavior(
                credentials_path=config.credentials_dir / config.tiktok_shop.credentials_file,
            )
        except (OSError, ValueError, KeyError, TypeError):
            pass

    if "bling" in configured_platform_keys:
        try:
            registry["bling"] = BlingUIBehavior(
                credentials_path=config.credentials_dir / config.bling.credentials_file,
            )
        except (OSError, ValueError, KeyError, TypeError):
            pass

    for platform in config.platforms:
        if not platform.key.startswith("omie"):
            continue

        if platform.key == "omie_2025":
            credentials_path = omie_2025_credentials_path
        elif platform.key == "omie_cfo":
            credentials_path = omie_cfo_credentials_path
        else:
            credentials_path = omie_2026_credentials_path

        if not credentials_path.exists():
            continue

        try:
            registry[platform.key] = OmieUIBehavior(
                credentials_path=credentials_path,
                platform_key=platform.key,
            )
        except (OSError, ValueError, KeyError, TypeError):
            continue

    for platform in config.platforms:
        registry.setdefault(platform.key, PlatformUIBehavior(platform_key=platform.key))

    return registry
