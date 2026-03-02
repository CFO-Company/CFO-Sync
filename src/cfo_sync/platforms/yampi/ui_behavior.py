from __future__ import annotations

from datetime import date
from pathlib import Path

from cfo_sync.core.models import RawRecord
from cfo_sync.platforms.ui_behavior import PlatformUIBehavior
from cfo_sync.platforms.yampi.credentials import YampiCredentialsStore
from cfo_sync.platforms.yampi.sku import search_sku_rows


class YampiUIBehavior(PlatformUIBehavior):
    def __init__(self, credentials_path: Path) -> None:
        super().__init__(platform_key="yampi")
        self.credentials_store = YampiCredentialsStore.from_file(credentials_path)

    @property
    def supports_sku_workflow(self) -> bool:
        return True

    def companies(self, configured_clients: list[str]) -> list[str]:
        return self.credentials_store.companies()

    def sub_client_names(self, company_name: str) -> list[str]:
        return self.credentials_store.alias_names_for_company(company_name)

    def uses_dedicated_resource_tab(self, resource_name: str) -> bool:
        return resource_name.lower() == "sku"

    def normalize_period(
        self,
        resource_name: str,
        start_date: date,
        end_date: date,
        today: date,
    ) -> tuple[date, date]:
        return start_date, end_date

    def search_sku_rows(
        self,
        company_name: str,
        order_number: str,
        selected_sub_clients: list[str] | None,
    ) -> tuple[list[RawRecord], list[str]]:
        alias_credentials = self.credentials_store.aliases_for_company(company_name)
        if selected_sub_clients:
            selected_set = {name.strip() for name in selected_sub_clients if name.strip()}
            alias_credentials = [
                credential for credential in alias_credentials if credential.alias in selected_set
            ]

        if not alias_credentials:
            raise ValueError("Nenhum alias selecionado para buscar SKU.")

        return search_sku_rows(
            alias_credentials=alias_credentials,
            order_number=order_number,
        )
