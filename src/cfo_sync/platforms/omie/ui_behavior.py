from __future__ import annotations

from pathlib import Path

from cfo_sync.platforms.omie.credentials import OmieCredentialsStore
from cfo_sync.platforms.ui_behavior import PlatformUIBehavior


class OmieUIBehavior(PlatformUIBehavior):
    def __init__(self, credentials_path: Path, platform_key: str = "omie") -> None:
        super().__init__(platform_key=platform_key)
        self.credentials_store = OmieCredentialsStore.from_file(credentials_path)

    def companies(self, configured_clients: list[str]) -> list[str]:
        return self.credentials_store.companies()

    def sub_client_names(self, company_name: str) -> list[str]:
        return self.credentials_store.alias_names_for_company(company_name)
