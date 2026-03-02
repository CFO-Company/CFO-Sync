from __future__ import annotations

from datetime import datetime
from typing import Any

from cfo_sync.core.models import RawRecord
from cfo_sync.platforms.yampi.api import fetch_orders_by_number
from cfo_sync.platforms.yampi.credentials import YampiAliasCredential


def search_sku_rows(
    alias_credentials: list[YampiAliasCredential],
    order_number: str,
) -> tuple[list[RawRecord], list[str]]:
    number = str(order_number).strip()
    if not number:
        return [], []

    found_orders: list[dict[str, Any]] = []
    found_aliases: list[str] = []
    for credential in alias_credentials:
        orders = fetch_orders_by_number(credential=credential, order_number=number)
        matched_orders = [order for order in orders if _order_matches_number(order, number)]
        if matched_orders:
            found_orders.extend(matched_orders)
            found_aliases.append(credential.alias)

    if not found_orders:
        return [], []

    rows: list[RawRecord] = []
    for order in found_orders:
        rows.extend(build_sku_rows_from_order(order))

    unique_rows: dict[tuple[str, str, str, str, str, float], RawRecord] = {}
    for row in rows:
        key = (
            str(row.get("number", "")),
            str(row.get("created_at", "")),
            str(row.get("sku_id", "")),
            str(row.get("item_sku", "")),
            str(row.get("quantity", "")),
            float(row.get("price_cost", 0.0)),
        )
        if key not in unique_rows:
            unique_rows[key] = row

    return list(unique_rows.values()), found_aliases


def build_sku_rows_from_order(order: dict[str, Any]) -> list[RawRecord]:
    order_number = str(order.get("number") or order.get("id") or "").strip()
    created_at = _to_order_created_at(order)
    rows: list[RawRecord] = []

    for raw_item in _extract_items_from_order(order):
        raw_sku_wrapper = raw_item.get("sku")
        raw_sku: dict[str, Any] = {}
        if isinstance(raw_sku_wrapper, dict):
            nested = raw_sku_wrapper.get("data")
            if isinstance(nested, dict):
                raw_sku = nested

        sku_id = raw_item.get("sku_id") or raw_sku.get("id")
        item_sku = raw_item.get("item_sku") or raw_sku.get("sku")
        quantity = raw_item.get("quantity") or 0
        price_cost = _to_sku_price_cost(raw_item, raw_sku)

        rows.append(
            {
                "number": order_number,
                "created_at": created_at,
                "sku_id": str(sku_id or "").strip(),
                "item_sku": str(item_sku or "").strip(),
                "quantity": int(quantity) if str(quantity).isdigit() else quantity,
                "price_cost": round(float(price_cost), 2),
            }
        )

    unique: dict[tuple[str, str, str, str, str, float], RawRecord] = {}
    for row in rows:
        key = (
            str(row["number"]),
            str(row["created_at"]),
            str(row["sku_id"]),
            str(row["item_sku"]),
            str(row["quantity"]),
            float(row["price_cost"]),
        )
        if key not in unique:
            unique[key] = row
    return list(unique.values())


def _to_sku_price_cost(raw_item: dict[str, Any], raw_sku: dict[str, Any]) -> float:
    for raw_value in (raw_item.get("price_cost"), raw_sku.get("price_cost"), raw_item.get("price")):
        if raw_value in (None, ""):
            continue
        try:
            return float(raw_value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _to_order_created_at(order: dict[str, Any]) -> str:
    raw_created_at = order.get("created_at")
    if isinstance(raw_created_at, dict):
        raw_date = raw_created_at.get("date")
        if raw_date not in (None, ""):
            return _format_to_ddmmyyyy(raw_date)
        return ""
    if raw_created_at in (None, ""):
        return ""
    return _format_to_ddmmyyyy(raw_created_at)


def _format_to_ddmmyyyy(raw_value: object) -> str:
    if raw_value in (None, ""):
        return ""

    text = str(raw_value).strip()
    if not text:
        return ""

    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).strftime("%d/%m/%Y")
    except ValueError:
        pass

    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue

    return text


def _extract_items_from_order(order: dict[str, Any]) -> list[dict[str, Any]]:
    items = order.get("items")
    if isinstance(items, dict):
        data = items.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    return []


def _order_matches_number(order: dict[str, Any], order_number: str) -> bool:
    candidate_number = str(order.get("number") or "").strip()
    candidate_id = str(order.get("id") or "").strip()
    number = order_number.strip()
    if not number:
        return False
    return candidate_number == number or candidate_id == number
