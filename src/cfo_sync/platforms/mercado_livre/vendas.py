from __future__ import annotations

from cfo_sync.core.models import RawRecord, ResourceConfig


def fetch_vendas_stub(client: str, resource: ResourceConfig) -> list[RawRecord]:
    return [
        {
            "client": client,
            "anuncio_id": "mlb-001",
            "titulo": "Anuncio Exemplo",
            "preco": 0,
            "resource": resource.name,
        }
    ]
