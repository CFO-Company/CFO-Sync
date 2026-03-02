from __future__ import annotations

from cfo_sync.core.models import RawRecord, ResourceConfig


def fetch_estoque_stub(client: str, resource: ResourceConfig) -> list[RawRecord]:
    return [
        {
            "client": client,
            "sku": "stub-sku-001",
            "nome_produto": "Produto Exemplo",
            "quantidade": 0,
            "resource": resource.name,
        }
    ]
