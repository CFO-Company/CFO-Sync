from __future__ import annotations

from pathlib import Path

from cfo_sync.platforms.bling.credentials import BlingCredentialsStore
from cfo_sync.platforms.ui_behavior import PlatformUIBehavior


class BlingUIBehavior(PlatformUIBehavior):
    def __init__(self, credentials_path: Path) -> None:
        super().__init__(platform_key="bling")
        self.credentials_path = credentials_path

    def companies(self, configured_clients: list[str]) -> list[str]:
        store = self._load_store()
        if store is None:
            return configured_clients
        companies = store.companies()
        return companies or configured_clients

    def sub_client_names(self, company_name: str) -> list[str]:
        store = self._load_store()
        if store is None:
            return []
        try:
            return store.account_names_for_company(company_name)
        except ValueError:
            return []

    def _load_store(self) -> BlingCredentialsStore | None:
        try:
            return BlingCredentialsStore.from_file(self.credentials_path)
        except (FileNotFoundError, ValueError, KeyError, TypeError):
            return None
