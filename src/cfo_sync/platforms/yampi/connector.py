from __future__ import annotations

from pathlib import Path

from cfo_sync.core.models import RawRecord, ResourceConfig
from cfo_sync.platforms.yampi.credentials import YampiCredentialsStore
from cfo_sync.platforms.yampi.estoque import fetch_estoque_stub
from cfo_sync.platforms.yampi.financeiro import fetch_financeiro


class YampiConnector:
    platform_key = "yampi"

    def __init__(self, credentials_path: Path) -> None:
        self.credentials_store = YampiCredentialsStore.from_file(credentials_path)

    def fetch(
        self,
        client: str,
        resource: ResourceConfig,
        start_date: str | None = None,
        end_date: str | None = None,
        sub_clients: list[str] | None = None,
    ) -> list[RawRecord]:
        aliases = self.credentials_store.aliases_for_company(client)

        if resource.name == "financeiro":
            return fetch_financeiro(
                client,
                resource,
                aliases,
                start_date=start_date,
                end_date=end_date,
                sub_clients=sub_clients,
            )
        if resource.name == "estoque":
            return fetch_estoque_stub(client, resource)
        return []
