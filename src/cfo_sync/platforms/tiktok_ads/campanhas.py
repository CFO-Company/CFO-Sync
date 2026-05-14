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

    rows_by_month: dict[tuple[str, str, str], RawRecord] = {}
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
            normalized_raw = _flatten_tiktok_report_row(raw)
            date_value = _resolve_iso_date(normalized_raw, fallback_date=since)
            mes_ano = _to_month_year(date_value)
            key = (client, account.account_name, mes_ano)
            row = rows_by_month.setdefault(
                key,
                {
                    "mes_ano": mes_ano,
                    "empresa": client,
                    "business_center_name": account.business_center_name,
                    "conta": account.account_name,
                    "tiktok_ads": 0.0,
                    "centro_custo": account.cost_center,
                    "tipo_ra": "Não Classificado",
                    "resource": resource.name,
                },
            )
            row["tiktok_ads"] = _round_currency(
                _to_float(row.get("tiktok_ads")) + _extract_spend(normalized_raw)
            )

    rows = list(rows_by_month.values())
    rows.sort(
        key=lambda item: (
            str(item.get("mes_ano") or ""),
            str(item.get("empresa") or ""),
            str(item.get("conta") or ""),
        )
    )
    return rows


def _extract_spend(raw: dict[str, Any]) -> float:
    return _first_float(
        raw,
        (
            "tiktok_ads",
            "spend",
            "stat_cost",
            "cost",
            "amount_spent",
            "metrics.spend",
            "metrics.stat_cost",
            "metrics.cost",
        ),
    )


def _flatten_tiktok_report_row(raw: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = dict(raw)
    _merge_nested_block(normalized, raw.get("dimensions"), prefix="dimensions")
    _merge_nested_block(normalized, raw.get("metrics"), prefix="metrics")
    _merge_nested_block(normalized, raw.get("metric"), prefix="metrics")
    _merge_nested_block(normalized, raw.get("stat_metrics"), prefix="metrics")
    return normalized


def _merge_nested_block(target: dict[str, Any], value: Any, prefix: str) -> None:
    if isinstance(value, list):
        for item in value:
            _merge_nested_block(target=target, value=item, prefix=prefix)
        return
    if not isinstance(value, dict):
        return

    for key, inner_value in value.items():
        normalized_key = str(key or "").strip()
        if not normalized_key:
            continue
        target.setdefault(normalized_key, inner_value)
        target[f"{prefix}.{normalized_key}"] = inner_value


def _resolve_iso_date(raw: dict[str, Any], fallback_date: str) -> str:
    raw_date = _first_text(
        raw,
        (
            "stat_time_day",
            "dimensions.stat_time_day",
            "date",
            "dimensions.date",
            "stat_datetime",
            "dimensions.stat_datetime",
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
