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
        payload_rows = iter_paginated(
            path=f"/act_{account.account_id}/insights",
            auth=auth,
            params={
                "fields": INSIGHTS_FIELDS,
                "level": "ad",
                "time_range": time_range,
                "limit": "500",
            },
        )
        for raw in payload_rows:
            row = _to_business_row(raw=raw, account=account, company_name=client, resource_name=resource.name)
            if row is not None:
                rows.append(row)

    return rows


def _to_business_row(
    raw: dict[str, Any],
    account: MetaAdsAccount,
    company_name: str,
    resource_name: str,
) -> RawRecord | None:
    ad_name = str(raw.get("ad_name") or "").strip()
    campaign_name = str(raw.get("campaign_name") or "").strip()
    date_raw = str(raw.get("date_start") or "").strip()
    spend_raw = raw.get("spend")

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
