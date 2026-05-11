from __future__ import annotations

from pathlib import Path

from cfo_sync.core.models import RawRecord, ResourceConfig
from cfo_sync.platforms.omie.credentials import OmieCredentialsStore
from cfo_sync.platforms.omie.financeiro import fetch_financeiro


class OmieConnector:
    platform_key = "omie"

    def __init__(self, credentials_path: Path) -> None:
        self.credentials_store = OmieCredentialsStore.from_file(credentials_path)

    def fetch(
        self,
        client: str,
        resource: ResourceConfig,
        start_date: str | None = None,
        end_date: str | None = None,
        sub_clients: list[str] | None = None,
    ) -> list[RawRecord]:
        credentials = self.credentials_store.credentials_for_company(client)

        if resource.name == "financeiro":
            return fetch_financeiro(
                client=client,
                resource=resource,
                credentials=credentials,
                start_date=start_date,
                end_date=end_date,
                sub_clients=sub_clients,
            )

        return []
