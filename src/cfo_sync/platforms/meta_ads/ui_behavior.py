from __future__ import annotations

from pathlib import Path

from cfo_sync.platforms.meta_ads.credentials import MetaAdsCredentialsStore
from cfo_sync.platforms.ui_behavior import PlatformUIBehavior


class MetaAdsUIBehavior(PlatformUIBehavior):
    def __init__(self, credentials_path: Path) -> None:
        super().__init__(platform_key="meta_ads")
        self.credentials_store = MetaAdsCredentialsStore.from_file(credentials_path)

    def companies(self, configured_clients: list[str]) -> list[str]:
        return self.credentials_store.companies()

    def sub_client_names(self, company_name: str) -> list[str]:
        return self.credentials_store.ad_account_names_for_company(company_name)
