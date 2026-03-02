from __future__ import annotations

from cfo_sync.core.models import RawRecord, ResourceConfig
from cfo_sync.platforms.meta_ads.credentials import MetaAdsAccount


def fetch_contas_stub(client: str, resource: ResourceConfig, accounts: list[MetaAdsAccount]) -> list[RawRecord]:
    rows: list[RawRecord] = []
    for account in accounts:
        rows.append(
            {
                "empresa": account.company_name,
                "bm": account.business_manager_name,
                "conta_anuncio": account.ad_account_name,
                "centro_custo": account.cost_center,
                "conta_id": account.account_id,
                "resource": resource.name,
            }
        )
    return rows
