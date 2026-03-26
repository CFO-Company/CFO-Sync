from __future__ import annotations

from datetime import datetime
from typing import Any

from cfo_sync.core.models import RawRecord, ResourceConfig
from cfo_sync.platforms.tiktok_ads.api import fetch_paginated_rows, normalize_period
from cfo_sync.platforms.tiktok_ads.credentials import (
    TikTokAdsAccount,
    TikTokAdsAuth,
    TikTokAdsCredentialsStore,
)


def fetch_campanhas(
    client: str,
    resource: ResourceConfig,
    accounts: list[TikTokAdsAccount],
    auth: TikTokAdsAuth,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[RawRecord]:
    since, until = normalize_period(start_date=start_date, end_date=end_date)

    aggregated_rows: dict[tuple[str, str, str], RawRecord] = {}
    for account in accounts:
        access_token = TikTokAdsCredentialsStore.access_token_for_account(account=account, auth=auth)
        raw_rows = fetch_paginated_rows(
            endpoint=resource.endpoint,
            access_token=access_token,
            advertiser_id=account.advertiser_id,
            start_date=since,
            end_date=until,
        )

        for raw in raw_rows:
            date_value = _resolve_iso_date(raw, fallback_date=since)
            mes_ano = _to_month_year(date_value)
            row_key = (mes_ano, client, account.account_name)

            row = aggregated_rows.get(row_key)
            if row is None:
                row = _build_base_row(
                    mes_ano=mes_ano,
                    empresa=client,
                    conta=account.account_name,
                    resource_name=resource.name,
                )
                aggregated_rows[row_key] = row

            metrics = _extract_metrics(raw)
            row["vendas_total"] = _round_currency(_to_float(row.get("vendas_total")) + metrics["vendas_total"])
            row["reembolso_total"] = _round_currency(
                _to_float(row.get("reembolso_total")) + metrics["reembolso_total"]
            )
            row["descontos_total"] = _round_currency(
                _to_float(row.get("descontos_total")) + metrics["descontos_total"]
            )
            row["cancelamento_total"] = _round_currency(
                _to_float(row.get("cancelamento_total")) + metrics["cancelamento_total"]
            )
            row["tarifas_total"] = _round_currency(
                _to_float(row.get("tarifas_total")) + metrics["tarifas_total"]
            )
            row["frete"] = _round_currency(_to_float(row.get("frete")) + metrics["frete"])
            row["tiktok_ads"] = _round_currency(_to_float(row.get("tiktok_ads")) + metrics["tiktok_ads"])

    rows = list(aggregated_rows.values())
    rows.sort(
        key=lambda item: (
            str(item.get("mes_ano") or ""),
            str(item.get("empresa") or ""),
            str(item.get("conta") or ""),
        )
    )
    return rows


def _build_base_row(
    mes_ano: str,
    empresa: str,
    conta: str,
    resource_name: str,
) -> RawRecord:
    return {
        "mes_ano": mes_ano,
        "empresa": empresa,
        "conta": conta,
        "vendas_total": 0.0,
        "reembolso_total": 0.0,
        "descontos_total": 0.0,
        "cancelamento_total": 0.0,
        "tarifas_total": 0.0,
        "frete": 0.0,
        "tiktok_ads": 0.0,
        "resource": resource_name,
    }


def _extract_metrics(raw: dict[str, Any]) -> dict[str, float]:
    return {
        "vendas_total": _first_float(
            raw,
            (
                "vendas_total",
                "sales_total",
                "total_sales",
                "gmv",
                "metrics.gmv",
                "metrics.total_sales",
            ),
        ),
        "reembolso_total": _first_float(
            raw,
            (
                "reembolso_total",
                "refund_total",
                "refund_amount",
                "total_refund",
                "metrics.refund",
                "metrics.refund_amount",
            ),
        ),
        "descontos_total": _first_float(
            raw,
            (
                "descontos_total",
                "discount_total",
                "discount_amount",
                "coupon_discount",
                "metrics.discount",
            ),
        ),
        "cancelamento_total": _first_float(
            raw,
            (
                "cancelamento_total",
                "cancellation_total",
                "cancel_total",
                "cancel_amount",
                "metrics.cancellation",
            ),
        ),
        "tarifas_total": _first_float(
            raw,
            (
                "tarifas_total",
                "fees_total",
                "fee_total",
                "service_fee",
                "commission_fee",
                "platform_fee",
                "metrics.fees",
            ),
        ),
        "frete": _first_float(
            raw,
            (
                "frete",
                "shipping_fee",
                "freight",
                "logistics_fee",
                "metrics.shipping_fee",
            ),
        ),
        "tiktok_ads": _first_float(
            raw,
            (
                "tiktok_ads",
                "spend",
                "stat_cost",
                "cost",
                "amount_spent",
                "metrics.spend",
                "metrics.cost",
            ),
        ),
    }


def _resolve_iso_date(raw: dict[str, Any], fallback_date: str) -> str:
    raw_date = _first_text(
        raw,
        (
            "stat_time_day",
            "date",
            "stat_datetime",
            "report_date",
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
        value = _get_by_path(raw, key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _first_float(raw: dict[str, Any], keys: tuple[str, ...]) -> float:
    for key in keys:
        value = _get_by_path(raw, key)
        parsed = _to_float(value)
        if parsed != 0.0:
            return parsed
    return 0.0


def _get_by_path(raw: dict[str, Any], path: str) -> Any:
    current: Any = raw
    for token in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(token)
    return current


def _to_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("R$", "").replace(" ", "")
    if "," in text and "." in text and text.rfind(",") > text.rfind("."):
        text = text.replace(".", "").replace(",", ".")
    elif "," in text and "." not in text:
        text = text.replace(",", ".")
    else:
        text = text.replace(",", "")
    try:
        return float(text)
    except ValueError:
        return 0.0


def _to_iso_date(raw_date: str) -> str:
    text = str(raw_date or "").strip()
    if not text:
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
    return text


def _round_currency(value: float) -> float:
    return round(float(value), 2)
