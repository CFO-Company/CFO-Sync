from __future__ import annotations

import logging
from pathlib import Path

from cfo_sync.core.models import RawRecord, ResourceConfig
from cfo_sync.platforms.google_ads.credentials import GoogleAdsCredentialsStore
from cfo_sync.platforms.google_ads.insights import fetch_insights

logger = logging.getLogger(__name__)


class GoogleAdsConnector:
    platform_key = "google_ads"

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

        if resource.name in {"contas", "insights", "campanhas"}:
            return fetch_insights(
                client=client,
                resource=resource,
                accounts=accounts,
                auth=store.auth,
                start_date=start_date,
                end_date=end_date,
            )

        return []

    def _load_store(self) -> GoogleAdsCredentialsStore | None:
        try:
            return GoogleAdsCredentialsStore.from_file(self.credentials_path)
        except (FileNotFoundError, ValueError, KeyError, TypeError) as error:
            logger.warning("Google Ads indisponivel: %s", error)
            return None
