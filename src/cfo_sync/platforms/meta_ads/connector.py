from __future__ import annotations

from pathlib import Path

from cfo_sync.core.models import RawRecord, ResourceConfig
from cfo_sync.platforms.meta_ads.contas import fetch_contas_stub
from cfo_sync.platforms.meta_ads.credentials import MetaAdsCredentialsStore
from cfo_sync.platforms.meta_ads.insights import fetch_insights


class MetaAdsConnector:
    platform_key = "meta_ads"

    def __init__(self, credentials_path: Path) -> None:
        self.credentials_store = MetaAdsCredentialsStore.from_file(credentials_path)

    def fetch(
        self,
        client: str,
        resource: ResourceConfig,
        start_date: str | None = None,
        end_date: str | None = None,
        sub_clients: list[str] | None = None,
    ) -> list[RawRecord]:
        accounts = self.credentials_store.accounts_for_company(client)
        if sub_clients:
            selected_names = {name.strip() for name in sub_clients if name.strip()}
            accounts = [account for account in accounts if account.ad_account_name in selected_names]

        if resource.name == "contas":
            return fetch_contas_stub(client, resource, accounts)
        if resource.name == "insights":
            return fetch_insights(
                client=client,
                resource=resource,
                accounts=accounts,
                auth=self.credentials_store.auth,
                start_date=start_date,
                end_date=end_date,
            )

        return []
