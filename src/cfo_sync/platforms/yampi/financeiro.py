from __future__ import annotations

from datetime import date
from typing import Any

from cfo_sync.core.models import RawRecord, ResourceConfig
from cfo_sync.platforms.yampi.api import fetch_orders_for_period, normalize_period
from cfo_sync.platforms.yampi.credentials import YampiAliasCredential


def fetch_financeiro(
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
        rows.extend(_aggregate_monthly(client, alias_credential.alias, orders, resource.name))

    rows.sort(key=lambda row: str(row["alias"]).lower())
    rows.sort(key=lambda row: _parse_row_date(str(row["data"])), reverse=True)
    return rows


def _aggregate_monthly(
    company_name: str,
    alias_name: str,
    orders: list[dict[str, Any]],
    resource_name: str,
) -> list[RawRecord]:
    bucket: dict[str, dict[str, Any]] = {}

    for order in orders:
        created = _extract_order_date(order.get("created_at"))
        if created is None:
            continue

        month_start = date(created.year, created.month, 1)
        month_key = month_start.isoformat()

        if month_key not in bucket:
            bucket[month_key] = {
                "data": month_start.strftime("%d/%m/%Y"),
                "nome_empresa": company_name,
                "alias": alias_name,
                "vendas_produto": 0.0,
                "descontos_concedidos": 0.0,
                "juros_venda": 0.0,
                "resource": resource_name,
            }

        month_row = bucket[month_key]
        value_products = _to_float(order.get("value_products"))
        value_shipment = _to_float(order.get("value_shipment"))
        value_discount = _to_float(order.get("value_discount"))
        value_tax = _to_float(order.get("value_tax"))

        month_row["vendas_produto"] += value_products + value_shipment
        month_row["descontos_concedidos"] += value_discount
        month_row["juros_venda"] += value_tax

    for row in bucket.values():
        row["vendas_produto"] = round(float(row["vendas_produto"]), 2)
        row["descontos_concedidos"] = round(float(row["descontos_concedidos"]), 2)
        row["juros_venda"] = round(float(row["juros_venda"]), 2)

    return list(bucket.values())


def _extract_order_date(raw_created_at: Any) -> date | None:
    raw_value = raw_created_at
    if isinstance(raw_created_at, dict):
        raw_value = raw_created_at.get("date")

    if not raw_value:
        return None

    text = str(raw_value).strip()
    if "T" in text:
        text = text.split("T", maxsplit=1)[0]
    elif " " in text:
        text = text.split(" ", maxsplit=1)[0]

    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _to_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().replace("R$", "").replace(" ", "")

    if "," in text and "." in text and text.rfind(",") > text.rfind("."):
        text = text.replace(".", "").replace(",", ".")
    elif "," in text and "." not in text:
        text = text.replace(",", ".")

    try:
        return float(text)
    except ValueError:
        return 0.0


def _parse_row_date(raw_date: str) -> date:
    return date.fromisoformat(f"{raw_date[6:10]}-{raw_date[3:5]}-{raw_date[0:2]}")
