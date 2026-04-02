from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from cfo_sync.core.models import RawRecord, ResourceConfig
from cfo_sync.platforms.meta_ads.api import iter_paginated, normalize_period
from cfo_sync.platforms.meta_ads.credentials import MetaAdsAccount, MetaAdsAuth


INSIGHTS_FIELDS = (
    "account_id,account_name,campaign_id,campaign_name,adset_id,adset_name,"
    "ad_id,ad_name,spend,date_start,date_stop"
)
ADSET_INSIGHTS_FIELDS = (
    "account_id,account_name,campaign_id,campaign_name,adset_id,adset_name,"
    "spend,date_start,date_stop"
)


def fetch_insights(
    client: str,
    resource: ResourceConfig,
    accounts: list[MetaAdsAccount],
    auth: MetaAdsAuth,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[RawRecord]:
    since, until = normalize_period(start_date, end_date)
    time_range = json.dumps({"since": since, "until": until}, separators=(",", ":"))

    rows: list[RawRecord] = []
    for account in accounts:
        ad_payload_rows = iter_paginated(
            path=f"/act_{account.account_id}/insights",
            auth=auth,
            params={
                "fields": INSIGHTS_FIELDS,
                "level": "ad",
                "time_increment": "1",
                "time_range": time_range,
                "limit": "500",
            },
        )
        for raw in ad_payload_rows:
            row = _to_business_row(raw=raw, account=account, company_name=client, resource_name=resource.name)
            if row is not None:
                rows.append(row)

        ad_spend_cents_by_key = _index_ad_spend_cents(ad_payload_rows)
        adset_payload_rows = iter_paginated(
            path=f"/act_{account.account_id}/insights",
            auth=auth,
            params={
                "fields": ADSET_INSIGHTS_FIELDS,
                "level": "adset",
                "time_increment": "1",
                "time_range": time_range,
                "limit": "500",
            },
        )
        rows.extend(
            _build_residual_adset_rows(
                adset_payload_rows=adset_payload_rows,
                ad_spend_cents_by_key=ad_spend_cents_by_key,
                account=account,
                company_name=client,
                resource_name=resource.name,
            )
        )

    return rows


def _build_residual_adset_rows(
    adset_payload_rows: list[dict[str, Any]],
    ad_spend_cents_by_key: dict[tuple[str, str, str], int],
    account: MetaAdsAccount,
    company_name: str,
    resource_name: str,
) -> list[RawRecord]:
    residual_rows: list[RawRecord] = []

    for raw in adset_payload_rows:
        key = _spend_key(raw)
        if key is None:
            continue

        adset_cents = _to_cents(raw.get("spend"))
        if adset_cents <= 0:
            continue

        ad_cents = ad_spend_cents_by_key.get(key, 0)
        residual_cents = adset_cents - ad_cents
        if residual_cents <= 0:
            continue

        synthetic_raw = dict(raw)
        synthetic_raw["ad_id"] = ""
        synthetic_raw["ad_name"] = _build_residual_ad_name(raw)
        synthetic_raw["spend"] = residual_cents / 100.0

        row = _to_business_row(
            raw=synthetic_raw,
            account=account,
            company_name=company_name,
            resource_name=resource_name,
        )
        if row is not None:
            residual_rows.append(row)

    return residual_rows


def _index_ad_spend_cents(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], int]:
    spend_cents_by_key: dict[tuple[str, str, str], int] = {}
    for raw in rows:
        key = _spend_key(raw)
        if key is None:
            continue
        spend_cents_by_key[key] = spend_cents_by_key.get(key, 0) + _to_cents(raw.get("spend"))
    return spend_cents_by_key


def _spend_key(raw: dict[str, Any]) -> tuple[str, str, str] | None:
    date_raw = str(raw.get("date_start") or "").strip()
    campaign_id = str(raw.get("campaign_id") or "").strip()
    campaign_name = str(raw.get("campaign_name") or "").strip()
    adset_id = str(raw.get("adset_id") or "").strip()
    adset_name = str(raw.get("adset_name") or "").strip()

    if not date_raw:
        return None

    campaign_token = campaign_id or f"campaign:{campaign_name}"
    adset_token = adset_id or f"adset:{adset_name}"
    if not campaign_token.strip() or not adset_token.strip():
        return None

    return date_raw, campaign_token, adset_token


def _build_residual_ad_name(raw: dict[str, Any]) -> str:
    adset_name = str(raw.get("adset_name") or "").strip()
    adset_id = str(raw.get("adset_id") or "").strip()
    campaign_name = str(raw.get("campaign_name") or "").strip()

    suffix = adset_name
    if not suffix and adset_id:
        suffix = f"ADSET {adset_id}"
    if not suffix:
        suffix = campaign_name or "Sem anuncio"
    return f"[SEM ANUNCIO] {suffix}"


def _to_business_row(
    raw: dict[str, Any],
    account: MetaAdsAccount,
    company_name: str,
    resource_name: str,
) -> RawRecord | None:
    ad_name = str(raw.get("ad_name") or "").strip()
    ad_id = str(raw.get("ad_id") or "").strip()
    campaign_name = str(raw.get("campaign_name") or "").strip()
    date_raw = str(raw.get("date_start") or "").strip()
    spend_raw = raw.get("spend")

    if not ad_name and ad_id:
        ad_name = f"AD {ad_id}"

    if not ad_name or not date_raw:
        return None

    parsed_date = _format_date_ddmmyyyy(date_raw)
    spend_value = _to_float(spend_raw)
    tipo_ra = _classify_tipo_ra(ad_name=ad_name, campaign_name=campaign_name)

    return {
        "nome_empresa": company_name,
        "nome_bm": account.business_manager_name,
        "nome_ca": account.ad_account_name,
        "nome_anuncio": ad_name,
        "valor_gasto": _format_brl(spend_value),
        "data": parsed_date,
        "centro_custo": account.cost_center,
        "tipo_ra": tipo_ra,
        "resource": resource_name,
    }


def _format_date_ddmmyyyy(raw_date: str) -> str:
    try:
        return datetime.strptime(raw_date, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return raw_date


def _format_brl(value: float) -> str:
    text = f"{value:,.2f}"
    text = text.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {text}"


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

    try:
        return float(text)
    except ValueError:
        return 0.0


def _to_cents(value: Any) -> int:
    return int(round(_to_float(value) * 100))


def _classify_tipo_ra(ad_name: str, campaign_name: str) -> str:
    # Mirror the same R/A logic used in exemple.js (optimized classifier).
    text = f"{ad_name} {campaign_name}".upper()

    if "[R]" in text:
        return "Retenção"
    if "[A]" in text:
        return "Aquisição"

    if re.search(r"RMKT|RTG|RET|CART|VISIT", text):
        return "Retenção"

    if re.search(r"CONV|ACQ|LEAD|PROSP", text):
        return "Aquisição"

    return "Não Classificado"
