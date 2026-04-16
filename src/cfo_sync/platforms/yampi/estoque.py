from __future__ import annotations

from cfo_sync.core.models import RawRecord, ResourceConfig
from cfo_sync.platforms.yampi.api import fetch_orders_for_period, normalize_period
from cfo_sync.platforms.yampi.credentials import YampiAliasCredential
from cfo_sync.platforms.yampi.sku import build_sku_rows_from_order


def fetch_estoque(
    client: str,
    resource: ResourceConfig,
    aliases: list[YampiAliasCredential],
    start_date: str | None = None,
    end_date: str | None = None,
    sub_clients: list[str] | None = None,
) -> list[RawRecord]:
    period_start, period_end = normalize_period(start_date, end_date)
    selected_aliases = aliases
    if sub_clients:
        selected_names = {name.strip() for name in sub_clients if name.strip()}
        selected_aliases = [credential for credential in aliases if credential.alias in selected_names]

    rows: list[RawRecord] = []
    for alias_credential in selected_aliases:
        orders = fetch_orders_for_period(
            credential=alias_credential,
            start_date=period_start,
            end_date=period_end,
        )
        for order in orders:
            sku_rows = build_sku_rows_from_order(order)
            for sku_row in sku_rows:
                sku_row["nome_empresa"] = client
                sku_row["alias"] = alias_credential.alias
                sku_row["resource"] = resource.name
                rows.append(sku_row)

    # Remove duplicidade para evitar linhas repetidas quando houver sobreposicao de pedidos.
    unique_rows: dict[tuple[str, str, str, str, str, str], RawRecord] = {}
    for row in rows:
        key = (
            str(row.get("number", "")),
            str(row.get("created_at", "")),
            str(row.get("sku_id", "")),
            str(row.get("item_sku", "")),
            str(row.get("quantity", "")),
            str(row.get("alias", "")),
        )
        if key not in unique_rows:
            unique_rows[key] = row

    return list(unique_rows.values())
