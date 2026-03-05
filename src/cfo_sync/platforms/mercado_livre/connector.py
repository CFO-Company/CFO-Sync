from __future__ import annotations

from pathlib import Path

from cfo_sync.core.models import RawRecord, ResourceConfig
from cfo_sync.platforms.mercado_livre.vendas import fetch_vendas


class MercadoLivreConnector:
    platform_key = "mercado_livre"

    def __init__(self, credentials_path: Path | None = None) -> None:
        self.credentials_path = credentials_path or Path("secrets/mercado_livre_credentials.json")

    def fetch(
        self,
        client: str,
        resource: ResourceConfig,
        start_date: str | None = None,
        end_date: str | None = None,
        sub_clients: list[str] | None = None,
    ) -> list[RawRecord]:
        if resource.name == "vendas":
            account_label_override = None
            if sub_clients:
                selected = [name.strip() for name in sub_clients if str(name).strip()]
                if selected:
                    account_label_override = selected[0]
            return fetch_vendas(
                client=client,
                resource=resource,
                credentials_path=self.credentials_path,
                start_date=start_date,
                end_date=end_date,
                account_label_override=account_label_override,
            )
        return []
