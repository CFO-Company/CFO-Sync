from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from cfo_sync.core.models import RawRecord, ResourceConfig
from cfo_sync.platforms.pagarme.api import flatten_record, list_charges, list_orders, normalize_period
from cfo_sync.platforms.pagarme.credentials import PagarmeAccount


def fetch_orders(
    *,
    client: str,
    resource: ResourceConfig,
    accounts: list[PagarmeAccount],
    start_date: str | None = None,
    end_date: str | None = None,
    sub_clients: list[str] | None = None,
) -> list[RawRecord]:
    since, until = normalize_period(start_date=start_date, end_date=end_date)
    selected_accounts = _filter_accounts(accounts=accounts, sub_clients=sub_clients)

    rows: list[RawRecord] = []
    for account in selected_accounts:
        raw_rows = list_orders(account=account, start_date=since, end_date=until)
        charge_totals_by_order = _charge_totals_by_order(
            account=account,
            start_date=since,
            end_date=until,
        )
        for raw in raw_rows:
            rows.append(
                _build_order_row(
                    client=client,
                    account=account,
                    resource=resource,
                    raw=raw,
                    charge_totals=charge_totals_by_order,
                )
            )

    rows.sort(
        key=lambda item: (
            str(item.get("mes_ano") or ""),
            str(item.get("alias") or ""),
            str(item.get("code") or item.get("id") or ""),
        )
    )
    return rows


def _build_order_row(
    *,
    client: str,
    account: PagarmeAccount,
    resource: ResourceConfig,
    raw: dict[str, Any],
    charge_totals: dict[str, dict[str, int]],
) -> RawRecord:
    flat = flatten_record(raw)
    row: RawRecord = dict(flat)
    row["nome_empresa"] = client
    row["alias"] = account.account_name
    row["conta"] = account.account_name
    row["account_id"] = account.account_id
    row["public_key"] = account.public_key
    row["resource"] = resource.name
    row["resource_source"] = "orders"
    row["raw_json"] = json.dumps(raw, ensure_ascii=False, sort_keys=True)

    row["id"] = _first_text(flat, ("id", "order_id"))
    row["pedido_id"] = row["id"]
    row["code"] = _first_text(flat, ("code",))
    row["status"] = _first_text(flat, ("status",))
    row["created_at"] = _first_text(flat, ("created_at", "createdAt", "created"))
    row["updated_at"] = _first_text(flat, ("updated_at", "updatedAt"))
    row["closed_at"] = _first_text(flat, ("closed_at", "closedAt"))
    row["customer_id"] = _first_text(
        flat,
        ("customer.id", "customer_id", "customer.code", "customer.customer_id"),
    )
    row["customer_name"] = _first_text(
        flat,
        ("customer.name", "customer_name", "customer.full_name"),
    )
    row["customer_email"] = _first_text(
        flat,
        ("customer.email", "customer_email"),
    )
    row["amount_centavos"] = _to_int(flat.get("amount"))
    row["amount_reais"] = _to_money(flat.get("amount"))
    totals = charge_totals.get(str(row["id"] or "").strip(), {})
    row["fee_centavos"] = totals.get("fee_centavos", 0)
    row["fee_reais"] = _to_money(row["fee_centavos"])
    row["taxa_pagarme_centavos"] = row["fee_centavos"]
    row["taxa_pagarme_reais"] = row["fee_reais"]
    row["paid_amount_centavos"] = totals.get("paid_amount_centavos", 0)
    row["paid_amount_reais"] = _to_money(row["paid_amount_centavos"])
    row["net_amount_centavos"] = totals.get("net_amount_centavos", 0)
    row["net_amount_reais"] = _to_money(row["net_amount_centavos"])
    row["refunded_amount_centavos"] = totals.get("refunded_amount_centavos", 0)
    row["refunded_amount_reais"] = _to_money(row["refunded_amount_centavos"])
    row["charges_count"] = totals.get("charges_count", 0)
    row["items_count"] = _count_list(raw.get("items"))
    row["payments_count"] = _count_list(raw.get("payments"))
    row["data"] = _resolve_data(
        row,
        ("created_at", "closed_at", "updated_at"),
    )
    row["mes_ano"] = _to_month_year(str(row.get("data") or ""))
    return row


def _charge_totals_by_order(
    *,
    account: PagarmeAccount,
    start_date: str,
    end_date: str,
) -> dict[str, dict[str, int]]:
    totals_by_order: dict[str, dict[str, int]] = {}
    for charge in list_charges(account=account, start_date=start_date, end_date=end_date):
        flat = flatten_record(charge)
        order_id = _first_text(flat, ("order_id", "order.id"))
        if not order_id:
            continue

        totals = totals_by_order.setdefault(
            order_id,
            {
                "fee_centavos": 0,
                "paid_amount_centavos": 0,
                "net_amount_centavos": 0,
                "refunded_amount_centavos": 0,
                "charges_count": 0,
            },
        )
        totals["fee_centavos"] += _to_int(
            _first_present(flat, ("fee", "last_transaction.fee", "last_transaction.charge_fee"))
        )
        totals["paid_amount_centavos"] += _to_int(flat.get("paid_amount"))
        totals["net_amount_centavos"] += _to_int(
            _first_present(flat, ("net_amount", "last_transaction.net_amount"))
        )
        totals["refunded_amount_centavos"] += _to_int(flat.get("refunded_amount"))
        totals["charges_count"] += 1
    return totals_by_order


def _filter_accounts(
    *,
    accounts: list[PagarmeAccount],
    sub_clients: list[str] | None,
) -> list[PagarmeAccount]:
    if not sub_clients:
        return accounts

    selected = {name.strip() for name in sub_clients if name and str(name).strip()}
    if not selected:
        return []

    return [account for account in accounts if account.account_name in selected]


def _resolve_data(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = str(row.get(key) or "").strip()
        if value:
            parsed = _to_iso_date(value)
            if parsed:
                return parsed
            return value
    return ""


def _to_month_year(iso_date: str) -> str:
    text = str(iso_date or "").strip()
    if not text:
        return ""
    try:
        parsed = datetime.strptime(text[:10], "%Y-%m-%d")
    except ValueError:
        return text
    return parsed.strftime("%m/%Y")


def _to_iso_date(raw_date: str) -> str:
    text = str(raw_date or "").strip()
    if not text:
        return ""

    if text.isdigit():
        timestamp = int(text)
        if timestamp > 10_000_000_000:
            timestamp = timestamp // 1000
        try:
            return datetime.utcfromtimestamp(timestamp).date().isoformat()
        except (OSError, OverflowError, ValueError):
            return ""

    for format_mask in (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
    ):
        try:
            return datetime.strptime(text, format_mask).date().isoformat()
        except ValueError:
            continue
    return ""


def _to_int(value: object) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip()
    if not text:
        return 0
    if "." in text and "," in text and text.rfind(",") > text.rfind("."):
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", "")
    try:
        return int(float(text))
    except ValueError:
        return 0


def _to_money(value: object) -> float:
    amount = _to_int(value)
    return round(amount / 100.0, 2)


def _count_list(value: object) -> int:
    if isinstance(value, list):
        return len(value)
    return 0


def _first_text(raw: dict[str, object], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = raw.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _first_present(raw: dict[str, object], keys: tuple[str, ...]) -> object:
    for key in keys:
        value = raw.get(key)
        if value in (None, ""):
            continue
        return value
    return ""
