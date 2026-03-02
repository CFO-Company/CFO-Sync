from __future__ import annotations

from cfo_sync.core.models import RawRecord, ResourceConfig
from cfo_sync.platforms.tiktok_ads.campanhas import fetch_campanhas_stub


class TikTokAdsConnector:
    platform_key = "tiktok_ads"

    def fetch(
        self,
        client: str,
        resource: ResourceConfig,
        start_date: str | None = None,
        end_date: str | None = None,
        sub_clients: list[str] | None = None,
    ) -> list[RawRecord]:
        if resource.name == "campanhas":
            return fetch_campanhas_stub(client, resource)
        return []
