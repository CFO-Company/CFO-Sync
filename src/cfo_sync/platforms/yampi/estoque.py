from __future__ import annotations

from datetime import date
from typing import Any

from cfo_sync.core.models import RawRecord, ResourceConfig
from cfo_sync.platforms.yampi.api import fetch_orders_for_period, normalize_period
from cfo_sync.platforms.yampi.credentials import YampiAliasCredential


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

    aggregated: dict[tuple[str, str], RawRecord] = {}
    for alias_credential in selected_aliases:
        orders = fetch_orders_for_period(
            credential=alias_credential,
            start_date=period_start,
            end_date=period_end,
        )
        for order in orders:
            if not _should_include_order(order):
                continue

            mes_ano = _to_month_year(order.get("created_at"))
            if not mes_ano:
                continue

            for item in _extract_items_from_order(order):
                nome_produto = _extract_product_name(item)
                sku = _extract_item_sku(item)
                if not nome_produto and not sku:
                    continue
                quantity = _to_int(item.get("quantity"))
                if quantity <= 0:
                    continue

                receita_total_item = _extract_item_revenue(item, quantity)
                key = (mes_ano, sku if sku else f"__SEM_SKU__::{_normalize_text(nome_produto)}")

                row = aggregated.get(key)
                if row is None:
                    row = {
                        "mes_ano": mes_ano,
                        "nome_produto": nome_produto,
                        "sku": sku,
                        "qtd_vendida": 0,
                        "receita_total_sku": 0.0,
                        # Compatibilidade com layouts antigos.
                        "created_at": mes_ano,
                        "sku_id": sku,
                        "item_sku": sku,
                        "quantity": 0,
                        "price_cost": 0.0,
                        "number": "",
                        "nome_empresa": client,
                        "resource": resource.name,
                    }
                    aggregated[key] = row
                elif not str(row.get("nome_produto") or "").strip() and nome_produto:
                    row["nome_produto"] = nome_produto

                row["qtd_vendida"] = int(row["qtd_vendida"]) + quantity
                row["receita_total_sku"] = float(row["receita_total_sku"]) + receita_total_item
                row["quantity"] = int(row["quantity"]) + quantity
                row["price_cost"] = float(row["price_cost"]) + receita_total_item

    rows = list(aggregated.values())
    for row in rows:
        row["receita_total_sku"] = round(float(row["receita_total_sku"]), 2)
        row["price_cost"] = round(float(row["price_cost"]), 2)

    rows.sort(key=lambda row: str(row.get("sku", "")).casefold())
    rows.sort(key=lambda row: str(row.get("nome_produto", "")).casefold())
    rows.sort(key=lambda row: _parse_month_year(str(row.get("mes_ano", ""))), reverse=True)
    return rows


def _normalize_text(value: object) -> str:
    return str(value or "").strip().casefold()


def _to_month_year(raw_created_at: Any) -> str:
    created = _extract_order_date(raw_created_at)
    if created is None:
        return ""
    return created.strftime("%m/%Y")


def _parse_month_year(raw_value: str) -> date:
    text = str(raw_value or "").strip()
    if "/" not in text:
        return date.min
    month_text, year_text = text.split("/", maxsplit=1)
    try:
        month = int(month_text)
        year = int(year_text)
        return date(year, month, 1)
    except ValueError:
        return date.min


def _extract_order_date(raw_created_at: Any) -> date | None:
    raw_value = raw_created_at
    if isinstance(raw_created_at, dict):
        raw_value = raw_created_at.get("date")

    if raw_value is None or str(raw_value).strip() == "":
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


def _extract_items_from_order(order: dict[str, Any]) -> list[dict[str, Any]]:
    items = order.get("items")
    if isinstance(items, dict):
        nested = items.get("data")
        if isinstance(nested, list):
            return [item for item in nested if isinstance(item, dict)]
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    return []


def _extract_product_name(raw_item: dict[str, Any]) -> str:
    raw_product = raw_item.get("product")
    product_data: dict[str, Any] = {}
    if isinstance(raw_product, dict):
        nested = raw_product.get("data")
        if isinstance(nested, dict):
            product_data = nested
        else:
            product_data = raw_product

    candidates = (
        raw_item.get("name"),
        raw_item.get("title"),
        raw_item.get("product_name"),
        raw_item.get("product_title"),
        product_data.get("name"),
        product_data.get("title"),
    )
    for candidate in candidates:
        text = str(candidate or "").strip()
        if text:
            return text
    return ""


def _extract_item_sku(raw_item: dict[str, Any]) -> str:
    raw_sku = raw_item.get("sku")
    sku_data: dict[str, Any] = {}
    if isinstance(raw_sku, dict):
        nested = raw_sku.get("data")
        if isinstance(nested, dict):
            sku_data = nested
        else:
            sku_data = raw_sku

    candidates = (
        raw_item.get("item_sku"),
        raw_item.get("sku"),
        raw_item.get("sku_code"),
        raw_item.get("sku_id"),
        sku_data.get("sku"),
        sku_data.get("item_sku"),
        sku_data.get("id"),
    )
    for candidate in candidates:
        if candidate in (None, ""):
            continue
        if isinstance(candidate, (dict, list, tuple, set)):
            continue
        text = str(candidate).strip()
        if text:
            return text
    return ""


def _extract_item_revenue(raw_item: dict[str, Any], quantity: int) -> float:
    total_candidates = (
        raw_item.get("value_total"),
        raw_item.get("total"),
        raw_item.get("total_price"),
        raw_item.get("amount"),
        raw_item.get("subtotal"),
    )
    for candidate in total_candidates:
        value = _to_float(candidate)
        if value > 0:
            return value

    unit_price = _extract_item_unit_price(raw_item)
    if unit_price <= 0 or quantity <= 0:
        return 0.0
    return unit_price * quantity


def _extract_item_unit_price(raw_item: dict[str, Any]) -> float:
    raw_sku = raw_item.get("sku")
    sku_data: dict[str, Any] = {}
    if isinstance(raw_sku, dict):
        nested = raw_sku.get("data")
        if isinstance(nested, dict):
            sku_data = nested

    raw_product = raw_item.get("product")
    product_data: dict[str, Any] = {}
    if isinstance(raw_product, dict):
        nested = raw_product.get("data")
        if isinstance(nested, dict):
            product_data = nested

    candidates = (
        raw_item.get("price_sale"),
        raw_item.get("price"),
        raw_item.get("value"),
        raw_item.get("price_cost"),
        raw_item.get("unit_price"),
        sku_data.get("price_sale"),
        sku_data.get("price"),
        sku_data.get("value"),
        sku_data.get("price_cost"),
        product_data.get("price_sale"),
        product_data.get("price"),
    )
    for candidate in candidates:
        value = _to_float(candidate)
        if value > 0:
            return value
    return 0.0


def _to_int(value: Any) -> int:
    if value is None or value == "":
        return 0

    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)

    text = str(value).strip()
    if not text:
        return 0
    text = text.replace(",", ".")
    if "." in text and text.replace(".", "", 1).isdigit():
        try:
            return int(float(text))
        except ValueError:
            return 0
    if text.isdigit():
        return int(text)
    return 0


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


def _should_include_order(order: dict[str, Any]) -> bool:
    payment_values = _collect_order_field_values(order, "payment_date")
    has_payment_date = any(not _is_empty_field(value) for value in payment_values)
    if not has_payment_date:
        return False

    cancelled_values = _collect_order_field_values(order, "cancelled_date")
    has_cancelled_date = any(not _is_empty_field(value) for value in cancelled_values)
    if has_cancelled_date:
        return False

    return True


def _collect_order_field_values(order: dict[str, Any], field_name: str) -> list[Any]:
    values: list[Any] = []
    if field_name in order:
        values.append(order.get(field_name))

    spreadsheet = order.get("spreadsheet")
    if isinstance(spreadsheet, dict):
        rows = spreadsheet.get("data")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict) and field_name in row:
                    values.append(row.get(field_name))

    if not values:
        values.append(None)
    return values


def _is_empty_field(value: Any) -> bool:
    if value is None:
        return True

    if isinstance(value, dict):
        if not value:
            return True
        if "date" in value:
            return _is_empty_field(value.get("date"))
        return False

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"", "null", "none"}:
            return True
        if normalized.startswith("0000-00-00"):
            return True
        return False

    return False
