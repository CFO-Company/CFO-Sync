from __future__ import annotations

from cfo_sync.core.models import RawRecord, ResourceConfig


def fetch_campanhas_stub(client: str, resource: ResourceConfig) -> list[RawRecord]:
    return [
        {
            "client": client,
            "campaign_id": "tt-001",
            "campaign_name": "Campanha Exemplo",
            "spend": 0,
            "resource": resource.name,
        }
    ]
