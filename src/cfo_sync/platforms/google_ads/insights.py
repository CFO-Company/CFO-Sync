from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any

from cfo_sync.core.models import RawRecord, ResourceConfig
from cfo_sync.platforms.google_ads.api import (
    GoogleAdsAPIError,
    normalize_period,
    search_stream,
)
from cfo_sync.platforms.google_ads.credentials import GoogleAdsAccount, GoogleAdsAuth

logger = logging.getLogger(__name__)


def fetch_insights(
    client: str,
    resource: ResourceConfig,
    accounts: list[GoogleAdsAccount],
    auth: GoogleAdsAuth,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[RawRecord]:
    since, until = normalize_period(start_date=start_date, end_date=end_date)

    deduped_rows: dict[tuple[str, str, str, str], RawRecord] = {}
    for account in accounts:
        ad_group_rows = _search_rows(
            auth=auth,
            account=account,
            query=_build_ad_group_daily_query(start_date=since, end_date=until),
            source_type="ad_group",
            required=False,
        )
        asset_group_rows = _search_rows(
            auth=auth,
            account=account,
            query=_build_asset_group_daily_query(start_date=since, end_date=until),
            source_type="asset_group",
            required=False,
        )

        raw_rows = [*ad_group_rows, *asset_group_rows]
        if not raw_rows:
            # Fallback quando a conta nao devolve entidades de grupo para o periodo.
            raw_rows = _search_rows(
                auth=auth,
                account=account,
                query=_build_campaign_daily_query(start_date=since, end_date=until),
                source_type="campaign",
                required=True,
            )

        for source_type, raw in raw_rows:
            row = _to_business_row(
                raw=raw,
                source_type=source_type,
                account=account,
                company_name=client,
                resource_name=resource.name,
            )
            if row is None:
                continue
            row_key = (
                str(row.get("date") or ""),
                str(row.get("customer_id") or ""),
                str(row.get("campaign_id") or ""),
                str(row.get("entity_key") or ""),
            )
            if not all(row_key):
                continue
            deduped_rows[row_key] = row

    rows = list(deduped_rows.values())
    rows.sort(
        key=lambda item: (
            str(item.get("date") or ""),
            str(item.get("campaign_id") or ""),
            str(item.get("ad_name") or ""),
        )
    )
    logger.info(
        "Google Ads: empresa=%s contas=%s linhas=%s periodo=%s..%s",
        client,
        len(accounts),
        len(rows),
        since,
        until,
    )
    return rows


def _search_rows(
    auth: GoogleAdsAuth,
    account: GoogleAdsAccount,
    query: str,
    source_type: str,
    required: bool,
) -> list[tuple[str, dict[str, Any]]]:
    try:
        payload_rows = search_stream(
            auth=auth,
            customer_id=account.customer_id,
            query=query,
        )
    except GoogleAdsAPIError as error:
        if required:
            raise GoogleAdsAPIError(
                f"Erro ao consultar Google Ads para conta '{account.account_name}' "
                f"(customer_id={account.customer_id}): {error}"
            ) from error
        logger.warning(
            "Google Ads: consulta opcional falhou para conta=%s customer_id=%s fonte=%s erro=%s",
            account.account_name,
            account.customer_id,
            source_type,
            error,
        )
        return []

    return [
        (source_type, row)
        for row in payload_rows
        if isinstance(row, dict)
    ]


def _build_ad_group_daily_query(start_date: str, end_date: str) -> str:
    return (
        "SELECT "
        "segments.date, "
        "customer.id, "
        "customer.descriptive_name, "
        "campaign.id, "
        "campaign.name, "
        "ad_group.id, "
        "ad_group.name, "
        "metrics.impressions, "
        "metrics.clicks, "
        "metrics.cost_micros, "
        "metrics.conversions "
        "FROM ad_group "
        f"WHERE segments.date BETWEEN '{start_date}' AND '{end_date}' "
        "AND campaign.status != 'REMOVED' "
        "AND ad_group.status != 'REMOVED' "
        "ORDER BY segments.date ASC, campaign.id ASC, ad_group.id ASC"
    )


def _build_asset_group_daily_query(start_date: str, end_date: str) -> str:
    return (
        "SELECT "
        "segments.date, "
        "customer.id, "
        "customer.descriptive_name, "
        "campaign.id, "
        "campaign.name, "
        "asset_group.id, "
        "asset_group.name, "
        "metrics.impressions, "
        "metrics.clicks, "
        "metrics.cost_micros, "
        "metrics.conversions "
        "FROM asset_group "
        f"WHERE segments.date BETWEEN '{start_date}' AND '{end_date}' "
        "AND campaign.status != 'REMOVED' "
        "AND asset_group.status != 'REMOVED' "
        "ORDER BY segments.date ASC, campaign.id ASC, asset_group.id ASC"
    )


def _build_campaign_daily_query(start_date: str, end_date: str) -> str:
    return (
        "SELECT "
        "segments.date, "
        "customer.id, "
        "customer.descriptive_name, "
        "campaign.id, "
        "campaign.name, "
        "metrics.impressions, "
        "metrics.clicks, "
        "metrics.cost_micros, "
        "metrics.conversions "
        "FROM campaign "
        f"WHERE segments.date BETWEEN '{start_date}' AND '{end_date}' "
        "AND campaign.status != 'REMOVED' "
        "ORDER BY segments.date ASC, campaign.id ASC"
    )


def _to_business_row(
    raw: dict[str, Any],
    source_type: str,
    account: GoogleAdsAccount,
    company_name: str,
    resource_name: str,
) -> RawRecord | None:
    customer_block = _ensure_dict(raw.get("customer"))
    campaign_block = _ensure_dict(raw.get("campaign"))
    metrics_block = _ensure_dict(raw.get("metrics"))
    segments_block = _ensure_dict(raw.get("segments"))
    ad_group_block = _ensure_dict(raw.get("adGroup") or raw.get("ad_group"))
    asset_group_block = _ensure_dict(raw.get("assetGroup") or raw.get("asset_group"))

    date_value = str(segments_block.get("date") or "").strip()
    campaign_id = _to_text(campaign_block.get("id"))
    campaign_name = _to_text(campaign_block.get("name"))
    customer_id = _to_text(customer_block.get("id")) or account.customer_id
    customer_name = _to_text(customer_block.get("descriptiveName")) or account.account_name
    impressions = _to_int(metrics_block.get("impressions"))
    clicks = _to_int(metrics_block.get("clicks"))
    cost_micros = _to_int(metrics_block.get("costMicros"))
    conversions = _to_float(metrics_block.get("conversions"))
    ad_name, entity_id = _resolve_ad_name_and_entity_id(
        source_type=source_type,
        campaign_name=campaign_name,
        ad_group=ad_group_block,
        asset_group=asset_group_block,
    )
    tipo_ra = _classify_tipo_ra(
        campaign_name=campaign_name,
        ad_name=ad_name,
        account_name=customer_name,
    )

    if not date_value or not campaign_id:
        return None
    if source_type in {"ad_group", "asset_group"} and not ad_name:
        return None

    nome_ca = customer_name or account.account_name
    valor_gasto = round(cost_micros / 1_000_000, 6)
    entity_key = f"{source_type}:{entity_id or ad_name or campaign_id}"

    return {
        "company_name": company_name,
        "account_name": account.account_name,
        "manager_account_name": account.manager_account_name,
        "cost_center": account.cost_center,
        "customer_id": customer_id,
        "customer_name": customer_name,
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "ad_name": ad_name,
        "entity_id": entity_id,
        "entity_key": entity_key,
        "source_type": source_type,
        "date": date_value,
        "impressions": impressions,
        "clicks": clicks,
        # Google Ads devolve custo em micros; converter para unidade monetaria.
        "cost": valor_gasto,
        "cost_micros": cost_micros,
        "conversions": conversions,
        "resource": resource_name,
        # Campos espelho para compatibilidade com o layout atual do Sheets.
        "nome_ca": nome_ca,
        "nome_campanha": campaign_name,
        "nome_anuncio": ad_name,
        "valor_gasto": valor_gasto,
        "data_gasto": date_value,
        "tipo_ra": tipo_ra,
        "centro_custo": account.cost_center,
    }


def _ensure_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _to_text(value: Any) -> str:
    return str(value or "").strip()


def _to_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip().replace(",", "")
    try:
        return int(float(text))
    except ValueError:
        return 0


def _to_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    try:
        return float(text)
    except ValueError:
        return 0.0


def _resolve_ad_name_and_entity_id(
    source_type: str,
    campaign_name: str,
    ad_group: dict[str, Any],
    asset_group: dict[str, Any],
) -> tuple[str, str]:
    if source_type == "ad_group":
        name = _to_text(ad_group.get("name"))
        entity_id = _to_text(ad_group.get("id"))
        return name, entity_id

    if source_type == "asset_group":
        name = _to_text(asset_group.get("name"))
        entity_id = _to_text(asset_group.get("id"))
        return name, entity_id

    # Fallback de campanha quando nao houver dados de grupo.
    return campaign_name, campaign_name


def _classify_tipo_ra(campaign_name: str, ad_name: str, account_name: str) -> str:
    tokens = [
        _normalize_text(account_name),
        _normalize_text(campaign_name),
        _normalize_text(ad_name),
    ]
    text = " ".join(token for token in tokens if token).upper()

    if any(token.startswith("[R]") for token in tokens if token) or "[R]" in text:
        return "Retenção"
    if any(token.startswith("[A]") for token in tokens if token) or "[A]" in text:
        return "Aquisição"

    retention_markers = (
        "REMARKETING|RETARGETING|RETENCAO|RETENCAO|RMKT|RMK|RTG|RET|RETE|"
        "CARRINHO|ABANDON|CRM|CLIENTE|CLIENTES|CUSTOMER|LOYAL|LOYALTY|"
        "WINBACK|WIN_BACK|REATIV|REACT|VISITED|VISIT|DYNAMIC|DINAMICO"
    )
    acquisition_markers = (
        "AQUISICAO|AQUISICAO|ACQ|ACQU|ACQUISITION|LEAD|LEADS|PROSP|PROSPECT|"
        "NEW|NOVO|NOVOS|CONV|CONVERSION|CONVERSAO|TRAFEGO|TRAFICO|TARGET|"
        "AWARE|AWARENESS|LOOKALIKE|LAL|GENERATION|GEN|BRANDING"
    )

    if re.search(retention_markers, text):
        return "Retenção"
    if re.search(acquisition_markers, text):
        return "Aquisição"

    if re.search(r"\[ADS\d+\]", text):
        return "Aquisição"
    if re.search(r"\d+", text) and re.search(r"CLIENTE|CLIENTES|CUSTOMER|CRM", text):
        return "Retenção"

    return "Não Classificado"


def _normalize_text(value: str) -> str:
    raw_text = str(value or "").strip()
    if not raw_text:
        return ""
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", raw_text)
        if not unicodedata.combining(char)
    )
    return without_accents
