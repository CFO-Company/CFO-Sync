from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from cfo_sync.core.models import RawRecord, ResourceConfig
from cfo_sync.platforms.mercado_pago.api import flatten_record, list_payments, normalize_period
from cfo_sync.platforms.mercado_pago.credentials import MercadoPagoAccount


def fetch_payments(
    *,
    client: str,
    resource: ResourceConfig,
    accounts: list[MercadoPagoAccount],
    start_date: str | None = None,
    end_date: str | None = None,
    sub_clients: list[str] | None = None,
) -> list[RawRecord]:
    since, until = normalize_period(start_date=start_date, end_date=end_date)
    selected_accounts = _filter_accounts(accounts=accounts, sub_clients=sub_clients)

    rows: list[RawRecord] = []
    for account in selected_accounts:
        raw_rows = list_payments(account=account, start_date=since, end_date=until)
        for raw in raw_rows:
            rows.append(
                _build_payment_row(
                    client=client,
                    account=account,
                    resource=resource,
                    raw=raw,
                )
            )

    rows.sort(
        key=lambda item: (
            str(item.get("mes_ano") or ""),
            str(item.get("alias") or ""),
            str(item.get("id") or ""),
        )
    )
    return rows


def _build_payment_row(
    *,
    client: str,
    account: MercadoPagoAccount,
    resource: ResourceConfig,
    raw: dict[str, Any],
) -> RawRecord:
    flat = flatten_record(raw)
    row: RawRecord = dict(flat)
    row["nome_empresa"] = client
    row["alias"] = account.account_name
    row["conta"] = account.account_name
    row["account_id"] = account.account_id
    row["public_key"] = account.public_key
    row["resource"] = resource.name
    row["resource_source"] = "payments"
    row["raw_json"] = json.dumps(raw, ensure_ascii=False, sort_keys=True)

    row["id"] = _first_text(flat, ("id", "payment_id"))
    row["pagamento_id"] = row["id"]
    row["status"] = _first_text(flat, ("status",))
    row["status_detail"] = _first_text(flat, ("status_detail",))
    row["payment_method_id"] = _first_text(flat, ("payment_method_id",))
    row["payment_type_id"] = _first_text(flat, ("payment_type_id",))
    row["external_reference"] = _first_text(flat, ("external_reference",))
    row["description"] = _first_text(flat, ("description",))
    row["date_created"] = _first_text(flat, ("date_created",))
    row["date_approved"] = _first_text(flat, ("date_approved",))
    row["date_last_updated"] = _first_text(flat, ("date_last_updated",))
    row["money_release_date"] = _first_text(flat, ("money_release_date",))
    row["transaction_amount"] = _to_float(flat.get("transaction_amount"))
    row["transaction_amount_refunded"] = _to_float(flat.get("transaction_amount_refunded"))
    row["installments"] = _to_int(flat.get("installments"))
    row["payer_id"] = _first_text(flat, ("payer.id", "payer_id"))
    row["payer_email"] = _first_text(flat, ("payer.email", "payer_email"))
    row["collector_id"] = _first_text(flat, ("collector_id",))
    row["data"] = _resolve_data(row, ("date_approved", "date_created", "date_last_updated"))
    row["mes_ano"] = _to_month_year(str(row.get("data") or ""))
    return row


def _filter_accounts(
    *,
    accounts: list[MercadoPagoAccount],
    sub_clients: list[str] | None,
) -> list[MercadoPagoAccount]:
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

    for format_mask in (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
    ):
        try:
            return datetime.strptime(text, format_mask).date().isoformat()
        except ValueError:
            continue
    return ""


def _to_int(value: object) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(float(str(value).strip().replace(",", ".")))
    except ValueError:
        return 0


def _to_float(value: object) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return round(float(str(value).strip().replace(",", ".")), 2)
    except ValueError:
        return 0.0


def _first_text(raw: dict[str, object], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = raw.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""
