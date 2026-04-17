from __future__ import annotations

from datetime import datetime
from typing import Any

from cfo_sync.core.models import RawRecord, ResourceConfig
from cfo_sync.platforms.tiktok_shop.api import fetch_paginated_rows, normalize_period
from cfo_sync.platforms.tiktok_shop.credentials import (
    TikTokShopAccount,
    TikTokShopAuth,
    TikTokShopCredentialsStore,
)


def fetch_orders(
    *,
    client: str,
    resource: ResourceConfig,
    accounts: list[TikTokShopAccount],
    auth: TikTokShopAuth,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[RawRecord]:
    since, until = normalize_period(start_date=start_date, end_date=end_date)

    rows: list[RawRecord] = []
    for account in accounts:
        access_token = TikTokShopCredentialsStore.access_token_for_account(account=account, auth=auth)
        shop_cipher = TikTokShopCredentialsStore.shop_cipher_for_account(account=account, auth=auth)
        shop_id = TikTokShopCredentialsStore.shop_id_for_account(account=account, auth=auth)
        raw_rows = fetch_paginated_rows(
            endpoint=resource.endpoint,
            auth=auth,
            access_token=access_token,
            shop_cipher=shop_cipher,
            shop_id=shop_id,
            start_date=since,
            end_date=until,
        )
        for raw in raw_rows:
            flat = _flatten_row(raw)
            iso_date = _resolve_iso_date(flat, fallback_date=since)
            flat.setdefault("data", iso_date)
            flat.setdefault("mes_ano", _to_month_year(iso_date))
            flat.setdefault("empresa", client)
            flat.setdefault("conta", account.account_name)
            flat.setdefault("shop_id", shop_id)
            flat.setdefault("shop_cipher", shop_cipher)
            flat.setdefault("resource", resource.name)
            rows.append(flat)

    rows.sort(
        key=lambda item: (
            str(item.get("mes_ano") or ""),
            str(item.get("empresa") or ""),
            str(item.get("conta") or ""),
            str(item.get("order_id") or item.get("id") or ""),
        )
    )
    return rows


def _flatten_row(raw: dict[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    _visit(prefix="", value=raw, target=flat)
    return flat


def _visit(*, prefix: str, value: Any, target: dict[str, Any]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key or "").strip()
            if not normalized_key:
                continue
            path = f"{prefix}.{normalized_key}" if prefix else normalized_key
            _visit(prefix=path, value=item, target=target)
        return

    if isinstance(value, list):
        target[prefix] = value
        return

    if prefix:
        target[prefix] = value
        leaf = prefix.rsplit(".", maxsplit=1)[-1]
        target.setdefault(leaf, value)


def _resolve_iso_date(raw: dict[str, Any], fallback_date: str) -> str:
    raw_date = _first_text(
        raw,
        (
            "create_time",
            "create_time_formatted",
            "create_time_str",
            "order_create_time",
            "order_time",
            "update_time",
            "payment_time",
            "data",
            "date",
        ),
    )
    return _to_iso_date(raw_date) or fallback_date


def _to_month_year(iso_date: str) -> str:
    text = str(iso_date or "").strip()
    if not text:
        return ""
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return text
    return parsed.strftime("%m/%Y")


def _first_text(raw: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = raw.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


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
