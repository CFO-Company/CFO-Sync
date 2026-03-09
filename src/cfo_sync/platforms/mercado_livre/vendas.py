from __future__ import annotations

import json
import re
import socket
import time
import unicodedata
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from cfo_sync.core.models import RawRecord, ResourceConfig
from cfo_sync.platforms.mercado_livre.oauth import MercadoLivreAPIError, ensure_valid_access_token


BASE_URL = "https://api.mercadolibre.com"
ORDERS_PAGE_SIZE = 50
BILLING_PAGE_SIZE = 1000
MAX_PAGES_SAFETY = 5000
RETRY_BACKOFF_SECONDS = (1.0, 3.0, 8.0)
BILLING_DOCUMENT_TYPE = "BILL"
TRANSACTION_DETAIL_MAP_PATH = Path(__file__).with_name("transaction_detail_map.json")

BILLING_CATEGORY_TO_FIELD = {
    "Meli Ads": "meli_ads",
    "Transporte - Mercadorias vendidas": "transporte_mercadorias_vendidas",
    "Tarifas de Marketplace": "tarifas_marketplace",
    "Fulfillment": "fulfillment",
}

_TRANSACTION_DETAIL_TO_FIELD: dict[str, str] | None = None


def fetch_vendas(
    client: str,
    resource: ResourceConfig,
    credentials_path: Path,
    start_date: str | None = None,
    end_date: str | None = None,
    account_label_override: str | None = None,
) -> list[RawRecord]:
    auth = ensure_valid_access_token(credentials_path, client=client)
    period_start, period_end = normalize_period(start_date, end_date)
    seller_id, account_label = _resolve_account(access_token=auth.access_token, fallback_user_id=auth.user_id)
    explicit_alias = str(account_label_override or auth.account_alias or "").strip()
    if explicit_alias:
        account_label = explicit_alias

    monthly_rows = _initialize_monthly_rows(
        client=client,
        account_label=account_label,
        resource_name=resource.name,
        period_start=period_start,
        period_end=period_end,
    )

    orders = _iter_orders(
        endpoint=resource.endpoint or "/orders/search",
        access_token=auth.access_token,
        seller_id=seller_id,
        period_start=period_start,
        period_end=period_end,
    )

    for order in orders:
        created_at = _to_date(order.get("date_created"))
        if created_at is None or created_at < period_start or created_at > period_end:
            continue
        if not _order_has_approved_date(order):
            continue

        month_key = _month_key(created_at)
        row = monthly_rows.get(month_key)
        if row is None:
            continue

        row["vendas_produto"] = float(row["vendas_produto"]) + _order_paid_total(order)

        row["reembolso_devolucoes"] = (
            float(row["reembolso_devolucoes"]) + _order_refund_total(order)
        )
        row["descontos_concedidos"] = (
            float(row["descontos_concedidos"]) + _order_discount_total(order)
        )

    month_boundaries = _iter_month_boundaries(period_start, period_end)
    unknown_transaction_details: set[str] = set()
    seen_billing_detail_ids: set[str] = set()
    billing_window_start = _month_first_day(period_start)
    billing_window_end = _next_month_first_day(_month_first_day(period_end))
    for billing_month_start, _billing_month_end in _iter_month_boundaries(
        billing_window_start,
        billing_window_end,
    ):
        billing_totals_by_month = _billing_fee_totals_by_month_and_field(
            access_token=auth.access_token,
            billing_month_start=billing_month_start,
            period_start=period_start,
            period_end=period_end,
            seen_detail_ids=seen_billing_detail_ids,
            unknown_transaction_details=unknown_transaction_details,
        )
        for month_key, billing_totals in billing_totals_by_month.items():
            row = monthly_rows.get(month_key)
            if row is None:
                continue
            for field_name, total_value in billing_totals.items():
                row[field_name] = float(row[field_name]) + total_value

    for detail in sorted(unknown_transaction_details):
        print(
            "AVISO Mercado Livre: transaction_detail sem mapeamento em "
            f"{TRANSACTION_DETAIL_MAP_PATH.name}: "
            f"'{detail}'. Aplicado fallback para 'Tarifas de Marketplace'."
        )

    rows = [monthly_rows[key] for key in sorted(monthly_rows.keys(), key=_month_key_sort)]
    for row in rows:
        for amount_field in (
            "vendas_produto",
            "reembolso_devolucoes",
            "descontos_concedidos",
            "meli_ads",
            "transporte_mercadorias_vendidas",
            "tarifas_marketplace",
            "fulfillment",
        ):
            row[amount_field] = round(float(row[amount_field]), 2)
    return rows


def normalize_period(start_date: str | None, end_date: str | None) -> tuple[date, date]:
    today = date.today()
    default_start = today.replace(day=1)
    start = _parse_date(start_date, default_start)
    end = _parse_date(end_date, today)
    if start > end:
        raise ValueError("Data inicial nao pode ser maior que data final.")
    return start, end


def _initialize_monthly_rows(
    client: str,
    account_label: str,
    resource_name: str,
    period_start: date,
    period_end: date,
) -> dict[str, RawRecord]:
    rows: dict[str, RawRecord] = {}
    for month_start, _month_end in _iter_month_boundaries(period_start, period_end):
        key = _month_key(month_start)
        rows[key] = {
            "mes_ano": key,
            "empresa": client,
            "conta": account_label,
            "vendas_produto": 0.0,
            "reembolso_devolucoes": 0.0,
            "descontos_concedidos": 0.0,
            "meli_ads": 0.0,
            "transporte_mercadorias_vendidas": 0.0,
            "tarifas_marketplace": 0.0,
            "fulfillment": 0.0,
            "resource": resource_name,
        }
    return rows


def _resolve_account(access_token: str, fallback_user_id: str) -> tuple[str, str]:
    payload = _request_json(path="/users/me", access_token=access_token, params={})
    user_id = str(payload.get("id") or "").strip() or fallback_user_id.strip()
    if not user_id:
        raise MercadoLivreAPIError("Nao foi possivel resolver o user_id do Mercado Livre.")

    nickname = str(payload.get("nickname") or "").strip()
    account_label = nickname or user_id
    return user_id, account_label


def _iter_orders(
    endpoint: str,
    access_token: str,
    seller_id: str,
    period_start: date,
    period_end: date,
) -> list[dict[str, Any]]:
    try:
        return _iter_orders_no_split(
            endpoint=endpoint,
            access_token=access_token,
            seller_id=seller_id,
            period_start=period_start,
            period_end=period_end,
        )
    except MercadoLivreAPIError as error:
        if not _is_limit_maximum_exceeded(error):
            raise

    if period_start >= period_end:
        raise MercadoLivreAPIError(
            "Limite de paginação do Mercado Livre excedido mesmo em janela minima "
            f"({period_start.isoformat()})."
        )

    midpoint = period_start + (period_end - period_start) // 2
    left_orders = _iter_orders(
        endpoint=endpoint,
        access_token=access_token,
        seller_id=seller_id,
        period_start=period_start,
        period_end=midpoint,
    )
    right_orders = _iter_orders(
        endpoint=endpoint,
        access_token=access_token,
        seller_id=seller_id,
        period_start=midpoint + timedelta(days=1),
        period_end=period_end,
    )

    unique_orders: dict[str, dict[str, Any]] = {}
    merged_orders: list[dict[str, Any]] = []
    for order in (*left_orders, *right_orders):
        order_id = str(order.get("id") or "").strip()
        if not order_id:
            merged_orders.append(order)
            continue
        if order_id in unique_orders:
            continue
        unique_orders[order_id] = order
        merged_orders.append(order)
    return merged_orders


def _iter_orders_no_split(
    endpoint: str,
    access_token: str,
    seller_id: str,
    period_start: date,
    period_end: date,
) -> list[dict[str, Any]]:
    path = endpoint.strip() or "/orders/search"
    if not path.startswith("/"):
        path = f"/{path}"

    rows: list[dict[str, Any]] = []
    offset = 0
    page = 0
    from_filter = f"{period_start.isoformat()}T00:00:00.000-04:00"
    to_filter = f"{period_end.isoformat()}T23:59:59.999-04:00"

    while page < MAX_PAGES_SAFETY:
        payload = _request_json(
            path=path,
            access_token=access_token,
            params={
                "seller": seller_id,
                "sort": "date_desc",
                "limit": str(ORDERS_PAGE_SIZE),
                "offset": str(offset),
                "order.date_created.from": from_filter,
                "order.date_created.to": to_filter,
            },
        )

        current = [item for item in payload.get("results", []) if isinstance(item, dict)]
        rows.extend(current)

        paging = payload.get("paging") or {}
        total = _to_int(paging.get("total"), default=0)
        count = _to_int(paging.get("count"), default=len(current))
        if not current or count <= 0:
            break

        offset += count
        if offset >= total:
            break
        page += 1

    return rows


def _is_limit_maximum_exceeded(error: MercadoLivreAPIError) -> bool:
    text = str(error).casefold()
    return "limit.maximum_exceeded" in text or (
        "limit must be a lower or equal than 10000" in text
    )


def _billing_fee_totals_by_month_and_field(
    access_token: str,
    billing_month_start: date,
    period_start: date,
    period_end: date,
    seen_detail_ids: set[str],
    unknown_transaction_details: set[str] | None = None,
) -> dict[str, dict[str, float]]:
    path = f"/billing/integration/periods/key/{billing_month_start.isoformat()}/group/ML/details"
    from_id = 0
    page = 0
    totals_by_month: dict[str, dict[str, float]] = {}

    while page < MAX_PAGES_SAFETY:
        payload = _request_json(
            path=path,
            access_token=access_token,
            params={
                "document_type": BILLING_DOCUMENT_TYPE,
                "limit": str(BILLING_PAGE_SIZE),
                "from_id": str(from_id),
            },
        )

        results = payload.get("results")
        if not isinstance(results, list) or not results:
            break

        for entry in results:
            if not isinstance(entry, dict):
                continue

            charge_info = entry.get("charge_info")
            if not isinstance(charge_info, dict):
                continue

            raw_id = charge_info.get("detail_id")
            detail_id = str(raw_id).strip() if raw_id is not None else ""
            if detail_id and detail_id in seen_detail_ids:
                continue
            if detail_id:
                seen_detail_ids.add(detail_id)

            created_at = _to_date(charge_info.get("creation_date_time")) or billing_month_start
            if created_at < period_start or created_at > period_end:
                continue

            month_key = _month_key(created_at)
            totals = totals_by_month.setdefault(
                month_key,
                {
                    "meli_ads": 0.0,
                    "transporte_mercadorias_vendidas": 0.0,
                    "tarifas_marketplace": 0.0,
                    "fulfillment": 0.0,
                },
            )

            target_field = _billing_target_field(
                charge_info.get("transaction_detail"),
                unknown_transaction_details=unknown_transaction_details,
            )
            signed_amount = _billing_signed_detail_amount(
                detail_amount=charge_info.get("detail_amount"),
                detail_type=charge_info.get("detail_type"),
                charge_bonified_id=charge_info.get("charge_bonified_id"),
                transaction_detail=charge_info.get("transaction_detail"),
            )
            totals[target_field] = float(totals[target_field]) + signed_amount

        last_id = payload.get("last_id")
        if last_id in (None, "", from_id):
            break
        from_id = _to_int(last_id, default=from_id)
        page += 1

    return totals_by_month


def _billing_target_field(
    transaction_detail: Any,
    unknown_transaction_details: set[str] | None = None,
) -> str:
    normalized_detail = _normalize_text(transaction_detail)
    detail_map = _load_transaction_detail_map()
    if normalized_detail and normalized_detail in detail_map:
        return detail_map[normalized_detail]

    if unknown_transaction_details is not None:
        original_detail = str(transaction_detail).strip() if transaction_detail is not None else ""
        unknown_transaction_details.add(original_detail or "<vazio>")
    return "tarifas_marketplace"


def _billing_signed_detail_amount(
    detail_amount: Any,
    detail_type: Any,
    charge_bonified_id: Any,
    transaction_detail: Any,
) -> float:
    amount = _to_float(detail_amount)
    magnitude = abs(amount)
    normalized_detail_type = str(detail_type or "").strip().upper()

    if normalized_detail_type == "CHARGE":
        return magnitude
    if normalized_detail_type == "BONUS":
        return -magnitude
    if amount < 0:
        return amount

    if _is_billing_reversal_detail(transaction_detail):
        return -magnitude

    has_charge_bonified = charge_bonified_id is not None and str(charge_bonified_id).strip() != ""
    return -magnitude if has_charge_bonified else magnitude


def _is_billing_reversal_detail(transaction_detail: Any) -> bool:
    normalized = _normalize_text(transaction_detail)
    if not normalized:
        return False
    return normalized.startswith(("cancelamento ", "estorno ", "anulacion ", "cancelacion "))


def _load_transaction_detail_map() -> dict[str, str]:
    global _TRANSACTION_DETAIL_TO_FIELD
    if _TRANSACTION_DETAIL_TO_FIELD is not None:
        return _TRANSACTION_DETAIL_TO_FIELD

    detail_map: dict[str, str] = {}
    if not TRANSACTION_DETAIL_MAP_PATH.exists():
        _TRANSACTION_DETAIL_TO_FIELD = detail_map
        return detail_map

    try:
        raw_mapping = json.loads(TRANSACTION_DETAIL_MAP_PATH.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        print(
            "AVISO Mercado Livre: arquivo de mapeamento invalido em "
            f"{TRANSACTION_DETAIL_MAP_PATH}."
        )
        _TRANSACTION_DETAIL_TO_FIELD = detail_map
        return detail_map

    if not isinstance(raw_mapping, dict):
        print(
            "AVISO Mercado Livre: arquivo de mapeamento deve ser um objeto JSON em "
            f"{TRANSACTION_DETAIL_MAP_PATH}."
        )
        _TRANSACTION_DETAIL_TO_FIELD = detail_map
        return detail_map

    invalid_categories: set[str] = set()
    for transaction_detail_text, mapped_value in raw_mapping.items():
        normalized_detail = _normalize_text(transaction_detail_text)
        category_name = str(mapped_value).strip()
        field_name = BILLING_CATEGORY_TO_FIELD.get(category_name)
        if field_name is None and category_name in BILLING_CATEGORY_TO_FIELD.values():
            field_name = category_name

        if normalized_detail and field_name:
            detail_map[normalized_detail] = field_name
        elif normalized_detail:
            invalid_categories.add(category_name or "<vazio>")

    if invalid_categories:
        ordered_invalid = ", ".join(sorted(invalid_categories))
        print(
            "AVISO Mercado Livre: categorias invalidas em "
            f"{TRANSACTION_DETAIL_MAP_PATH.name}: {ordered_invalid}."
        )

    _TRANSACTION_DETAIL_TO_FIELD = detail_map
    return detail_map


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    # Normaliza variacoes comuns da API (acentos, pontuacao e espacos),
    # para tornar o de/para robusto a pequenas diferencas de escrita.
    normalized = unicodedata.normalize("NFKD", text)
    without_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    alnum_spaces = re.sub(r"[^0-9A-Za-z]+", " ", without_accents)
    return " ".join(alnum_spaces.split()).casefold()


def _request_json(path: str, access_token: str, params: dict[str, str]) -> dict[str, Any]:
    url = f"{BASE_URL}{path}?{urlencode(params)}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }

    for backoff in (*RETRY_BACKOFF_SECONDS, None):
        request = Request(url=url, method="GET", headers=headers)
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            body = error.read().decode("utf-8", errors="ignore") if error.fp else ""
            if error.code in {429, 500, 502, 503, 504} and backoff is not None:
                wait_seconds = max(60.0, backoff) if error.code == 429 else backoff
                time.sleep(wait_seconds)
                continue
            raise MercadoLivreAPIError(
                f"Erro HTTP no Mercado Livre (status={error.code}): {body[:300]}"
            ) from error
        except (URLError, TimeoutError, socket.timeout) as error:
            if backoff is not None:
                time.sleep(backoff)
                continue
            raise MercadoLivreAPIError(f"Erro de conexao no Mercado Livre: {error}") from error
        except json.JSONDecodeError as error:
            raise MercadoLivreAPIError("Resposta invalida da API Mercado Livre.") from error

    raise MercadoLivreAPIError("Falha inesperada ao chamar Mercado Livre.")


def _order_refund_total(order: dict[str, Any]) -> float:
    payments = order.get("payments")
    if not isinstance(payments, list):
        return 0.0
    total = 0.0
    for payment in payments:
        if not isinstance(payment, dict):
            continue
        total += _to_float(payment.get("transaction_amount_refunded"))
    return total


def _order_has_approved_date(order: dict[str, Any]) -> bool:
    payments = order.get("payments")
    if not isinstance(payments, list) or not payments:
        return False

    for payment in payments:
        if not isinstance(payment, dict):
            continue
        approved = payment.get("date_approved")
        if approved is not None and str(approved).strip() != "":
            return True
    return False


def _order_paid_total(order: dict[str, Any]) -> float:
    payments = order.get("payments")
    if not isinstance(payments, list) or not payments:
        return _to_float(order.get("total_amount"))

    total = 0.0
    has_any_payment_amount = False
    for payment in payments:
        if not isinstance(payment, dict):
            continue
        if payment.get("total_paid_amount") not in (None, ""):
            has_any_payment_amount = True
        total += _to_float(payment.get("total_paid_amount"))

    if not has_any_payment_amount:
        return _to_float(order.get("total_amount"))
    return total


def _order_discount_total(order: dict[str, Any]) -> float:
    payments = order.get("payments")
    if isinstance(payments, list) and payments:
        total = 0.0
        has_any_coupon_amount = False
        for payment in payments:
            if not isinstance(payment, dict):
                continue
            if payment.get("coupon_amount") not in (None, ""):
                has_any_coupon_amount = True
            total += _to_float(payment.get("coupon_amount"))
        if has_any_coupon_amount:
            return total

    coupon = order.get("coupon")
    if isinstance(coupon, dict):
        return _to_float(coupon.get("amount"))
    return 0.0


def _order_shipping_total(order: dict[str, Any]) -> float:
    explicit_shipping = _to_float(order.get("shipping_cost"))
    if explicit_shipping:
        return explicit_shipping
    shipping = order.get("shipping")
    if isinstance(shipping, dict):
        return _to_float(shipping.get("cost"))
    return 0.0


def _iter_month_boundaries(start_date: date, end_date: date) -> list[tuple[date, date]]:
    boundaries: list[tuple[date, date]] = []
    current = date(start_date.year, start_date.month, 1)
    last = date(end_date.year, end_date.month, 1)
    while current <= last:
        month_end = _month_last_day(current)
        boundaries.append((current, month_end))
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return boundaries


def _month_first_day(day: date) -> date:
    return date(day.year, day.month, 1)


def _next_month_first_day(day: date) -> date:
    if day.month == 12:
        return date(day.year + 1, 1, 1)
    return date(day.year, day.month + 1, 1)


def _month_last_day(day: date) -> date:
    if day.month == 12:
        return date(day.year, 12, 31)
    next_month = date(day.year, day.month + 1, 1)
    return date.fromordinal(next_month.toordinal() - 1)


def _month_key(day: date) -> str:
    return day.strftime("%m/%Y")


def _month_key_sort(key: str) -> tuple[int, int]:
    month = int(key[0:2])
    year = int(key[3:7])
    return year, month


def _parse_date(raw_value: str | None, default_value: date) -> date:
    if raw_value is None or str(raw_value).strip() == "":
        return default_value
    return date.fromisoformat(str(raw_value))


def _to_date(raw_value: Any) -> date | None:
    if raw_value is None:
        return None
    text = str(raw_value).strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", maxsplit=1)[0]
    elif " " in text:
        text = text.split(" ", maxsplit=1)[0]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0
