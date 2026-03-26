from __future__ import annotations

import logging
from pathlib import Path

from cfo_sync.core.models import RawRecord, ResourceConfig
from cfo_sync.platforms.tiktok_ads.campanhas import fetch_campanhas
from cfo_sync.platforms.tiktok_ads.credentials import TikTokAdsCredentialsStore


logger = logging.getLogger(__name__)


class TikTokAdsConnector:
    platform_key = "tiktok_ads"

    def __init__(self, credentials_path: Path) -> None:
        self.credentials_path = credentials_path

    def fetch(
        self,
        client: str,
        resource: ResourceConfig,
        start_date: str | None = None,
        end_date: str | None = None,
        sub_clients: list[str] | None = None,
    ) -> list[RawRecord]:
        store = self._load_store()
        if store is None:
            return []

        accounts = store.accounts_for_company(client)
        if sub_clients:
            selected_names = {name.strip() for name in sub_clients if name.strip()}
            accounts = [account for account in accounts if account.account_name in selected_names]

        if not accounts:
            return []

        if resource.name in {"campanhas", "insights", "contas"}:
            return fetch_campanhas(
                client=client,
                resource=resource,
                accounts=accounts,
                auth=store.auth,
                start_date=start_date,
                end_date=end_date,
            )

        return []

    def _load_store(self) -> TikTokAdsCredentialsStore | None:
        try:
            return TikTokAdsCredentialsStore.from_file(self.credentials_path)
        except (FileNotFoundError, ValueError, KeyError, TypeError) as error:
            logger.warning("TikTok Ads indisponivel: %s", error)
            return None
