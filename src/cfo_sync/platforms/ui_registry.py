from __future__ import annotations

from cfo_sync.core.models import AppConfig
from cfo_sync.platforms.meta_ads.ui_behavior import MetaAdsUIBehavior
from cfo_sync.platforms.ui_behavior import PlatformUIBehavior
from cfo_sync.platforms.yampi.ui_behavior import YampiUIBehavior


def build_platform_ui_registry(config: AppConfig) -> dict[str, PlatformUIBehavior]:
    registry: dict[str, PlatformUIBehavior] = {
        "yampi": YampiUIBehavior(
            credentials_path=config.credentials_dir / config.yampi.credentials_file,
        ),
        "meta_ads": MetaAdsUIBehavior(
            credentials_path=config.credentials_dir / config.meta_ads.credentials_file,
        ),
    }

    for platform in config.platforms:
        registry.setdefault(platform.key, PlatformUIBehavior(platform_key=platform.key))

    return registry
