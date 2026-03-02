from __future__ import annotations

from cfo_sync.core.models import RawRecord, ResourceConfig
from cfo_sync.platforms.mercado_livre.vendas import fetch_vendas_stub


class MercadoLivreConnector:
    platform_key = "mercado_livre"

    def fetch(
        self,
        client: str,
        resource: ResourceConfig,
        start_date: str | None = None,
        end_date: str | None = None,
        sub_clients: list[str] | None = None,
    ) -> list[RawRecord]:
        if resource.name == "vendas":
            return fetch_vendas_stub(client, resource)
        return []
