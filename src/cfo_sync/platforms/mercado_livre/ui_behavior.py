from __future__ import annotations

from pathlib import Path

from cfo_sync.platforms.mercado_livre.credentials import MercadoLivreCredentialsStore
from cfo_sync.platforms.mercado_livre.oauth import ensure_valid_access_token
from cfo_sync.platforms.ui_behavior import PlatformUIBehavior


class MercadoLivreUIBehavior(PlatformUIBehavior):
    def __init__(self, credentials_path: Path) -> None:
        super().__init__(platform_key="mercado_livre")
        self.credentials_path = credentials_path

    def companies(self, configured_clients: list[str]) -> list[str]:
        try:
            companies = MercadoLivreCredentialsStore.companies(self.credentials_path)
        except (FileNotFoundError, ValueError, KeyError, TypeError):
            companies = []
        return companies or configured_clients

    def sub_client_names(self, company_name: str) -> list[str]:
        try:
            store = MercadoLivreCredentialsStore.from_file(
                self.credentials_path,
                company_name=company_name,
            )
        except (FileNotFoundError, ValueError):
            return []

        for account_label in store.account_labels:
            try:
                ensure_valid_access_token(
                    self.credentials_path,
                    client=company_name,
                    account_alias=account_label,
                )
            except Exception:  # noqa: BLE001
                continue

        try:
            store = MercadoLivreCredentialsStore.from_file(
                self.credentials_path,
                company_name=company_name,
            )
        except (FileNotFoundError, ValueError):
            return []
        return list(store.account_labels)
