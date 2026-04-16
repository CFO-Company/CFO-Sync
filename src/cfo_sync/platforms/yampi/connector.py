from __future__ import annotations

from pathlib import Path

from cfo_sync.core.models import RawRecord, ResourceConfig
from cfo_sync.platforms.yampi.credentials import YampiCredentialsStore
from cfo_sync.platforms.yampi.estoque import fetch_estoque
from cfo_sync.platforms.yampi.financeiro import fetch_financeiro


class YampiConnector:
    platform_key = "yampi"

    def __init__(self, credentials_path: Path) -> None:
        self.credentials_store = YampiCredentialsStore.from_file(credentials_path)
        self.estoque_credentials_path = credentials_path.with_name("yampi_estoque.json")
        self._estoque_credentials_store: YampiCredentialsStore | None = None

    def _get_estoque_credentials_store(self) -> YampiCredentialsStore:
        if self._estoque_credentials_store is None:
            self._estoque_credentials_store = YampiCredentialsStore.from_file(self.estoque_credentials_path)
        return self._estoque_credentials_store

    def fetch(
        self,
        client: str,
        resource: ResourceConfig,
        start_date: str | None = None,
        end_date: str | None = None,
        sub_clients: list[str] | None = None,
    ) -> list[RawRecord]:
        if resource.name == "financeiro":
            aliases = self.credentials_store.aliases_for_company(client)
            return fetch_financeiro(
                client,
                resource,
                aliases,
                start_date=start_date,
                end_date=end_date,
                sub_clients=sub_clients,
            )
        if resource.name == "estoque":
            aliases = self._get_estoque_credentials_store().aliases_for_company(client)
            return fetch_estoque(
                client,
                resource,
                aliases,
                start_date=start_date,
                end_date=end_date,
                sub_clients=sub_clients,
            )
        return []
