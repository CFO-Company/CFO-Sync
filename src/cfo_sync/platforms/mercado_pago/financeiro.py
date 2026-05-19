from __future__ import annotations

from cfo_sync.core.models import RawRecord, ResourceConfig
from cfo_sync.platforms.mercado_pago.credentials import MercadoPagoAccount
from cfo_sync.platforms.mercado_pago.payments import fetch_payments


def fetch_financeiro(
    *,
    client: str,
    resource: ResourceConfig,
    accounts: list[MercadoPagoAccount],
    start_date: str | None = None,
    end_date: str | None = None,
    sub_clients: list[str] | None = None,
) -> list[RawRecord]:
    rows = fetch_payments(
        client=client,
        resource=resource,
        accounts=accounts,
        start_date=start_date,
        end_date=end_date,
        sub_clients=sub_clients,
    )
    for row in rows:
        row["resource_source"] = "payments"
        row["valor_bruto"] = row.get("transaction_amount", 0.0)
        row["valor_reembolsado"] = row.get("transaction_amount_refunded", 0.0)
        row["valor_liquido"] = _to_float(row.get("transaction_details.net_received_amount"))
        row["total_pago"] = _to_float(row.get("transaction_details.total_paid_amount"))
        row["custo_financiamento"] = _to_float(row.get("fee_details"))
    return rows


def _to_float(value: object) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return round(float(str(value).strip().replace(",", ".")), 2)
    except ValueError:
        return 0.0
