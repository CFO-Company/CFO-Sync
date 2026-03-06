from __future__ import annotations

from cfo_sync.core.models import AppConfig
from cfo_sync.platforms.mercado_livre.ui_behavior import MercadoLivreUIBehavior
from cfo_sync.platforms.meta_ads.ui_behavior import MetaAdsUIBehavior
from cfo_sync.platforms.omie.credentials import OMIE_CREDENTIALS_PATH, resolve_omie_credentials_path
from cfo_sync.platforms.omie.ui_behavior import OmieUIBehavior
from cfo_sync.platforms.ui_behavior import PlatformUIBehavior
from cfo_sync.platforms.yampi.ui_behavior import YampiUIBehavior


def build_platform_ui_registry(config: AppConfig) -> dict[str, PlatformUIBehavior]:
    omie_credentials_path = resolve_omie_credentials_path(OMIE_CREDENTIALS_PATH)

    registry: dict[str, PlatformUIBehavior] = {
        "yampi": YampiUIBehavior(
            credentials_path=config.credentials_dir / config.yampi.credentials_file,
        ),
        "meta_ads": MetaAdsUIBehavior(
            credentials_path=config.credentials_dir / config.meta_ads.credentials_file,
        ),
        "mercado_livre": MercadoLivreUIBehavior(
            credentials_path=config.credentials_dir / "mercado_livre_credentials.json",
        ),
    }

    if omie_credentials_path is not None:
        registry["omie"] = OmieUIBehavior(credentials_path=omie_credentials_path)

    for platform in config.platforms:
        registry.setdefault(platform.key, PlatformUIBehavior(platform_key=platform.key))

    return registry
