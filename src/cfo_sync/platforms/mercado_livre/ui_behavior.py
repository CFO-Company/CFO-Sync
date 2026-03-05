from __future__ import annotations

from pathlib import Path

from cfo_sync.platforms.mercado_livre.credentials import MercadoLivreCredentialsStore
from cfo_sync.platforms.ui_behavior import PlatformUIBehavior


class MercadoLivreUIBehavior(PlatformUIBehavior):
    def __init__(self, credentials_path: Path) -> None:
        super().__init__(platform_key="mercado_livre")
        self.credentials_path = credentials_path

    def sub_client_names(self, company_name: str) -> list[str]:
        try:
            store = MercadoLivreCredentialsStore.from_file(
                self.credentials_path,
                company_name=company_name,
            )
        except (FileNotFoundError, ValueError):
            return []

        alias = store.auth.account_alias.strip()
        if not alias:
            return []
        return [alias]
