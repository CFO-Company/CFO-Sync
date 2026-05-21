from __future__ import annotations

import base64
import json
from datetime import date, datetime, time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from cfo_sync.platforms.pagarme.credentials import PagarmeAccount


DEFAULT_PAGE_SIZE = 100
USER_AGENT = "CFO-Sync/1.0"


class PagarmeAPIError(RuntimeError):
    pass


def normalize_period(start_date: str | None, end_date: str | None) -> tuple[str, str]:
    today = date.today()
    start = _parse_date(start_date, today.replace(day=1))
    end = _parse_date(end_date, today)
    if start > end:
        raise ValueError("Data inicial nao pode ser maior que data final.")
    return _start_of_day_iso(start), _end_of_day_iso(end)


def list_orders(
    account: PagarmeAccount,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    since, until = normalize_period(start_date, end_date)
    return _paginate(
        account=account,
        path="/orders",
        params={
            "created_since": since,
            "created_until": until,
            "page": 1,
            "size": DEFAULT_PAGE_SIZE,
        },
        items_keys=("orders", "data", "items"),
    )


def list_charges(
    account: PagarmeAccount,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    since, until = normalize_period(start_date, end_date)
    return _paginate(
        account=account,
        path="/charges",
        params={
            "created_since": since,
            "created_until": until,
            "page": 1,
            "size": DEFAULT_PAGE_SIZE,
        },
        items_keys=("charges", "data", "items"),
    )


def list_payables(
    account: PagarmeAccount,
    *,
    charge_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "page": 1,
        "size": DEFAULT_PAGE_SIZE,
    }
    if charge_id:
        params["charge_id"] = charge_id
    if start_date:
        params["created_since"] = start_date
    if end_date:
        params["created_until"] = end_date

    return _paginate(
        account=account,
        path="/payables",
        params=params,
        items_keys=("payables", "data", "items"),
    )


def get_order(account: PagarmeAccount, order_id: str) -> dict[str, Any]:
    return _call_json(account=account, path=f"/orders/{order_id}", params={})


def get_charge(account: PagarmeAccount, charge_id: str) -> dict[str, Any]:
    return _call_json(account=account, path=f"/charges/{charge_id}", params={})


def flatten_record(value: dict[str, Any]) -> dict[str, object]:
    flattened: dict[str, object] = {}
    _flatten_into(flattened, "", value)
    return flattened


def _paginate(
    *,
    account: PagarmeAccount,
    path: str,
    params: dict[str, Any],
    items_keys: tuple[str, ...],
) -> list[dict[str, Any]]:
    page = max(1, int(params.get("page") or 1))
    page_size = max(1, int(params.get("size") or DEFAULT_PAGE_SIZE))
    rows: list[dict[str, Any]] = []

    while True:
        request_params = dict(params)
        request_params["page"] = page
        request_params["size"] = page_size
        response = _call_json(account=account, path=path, params=request_params)
        items = _extract_items(response, items_keys)
        if not items:
            break

        rows.extend(items)
        total_pages = _extract_total_pages(response)
        if total_pages is not None:
            if page >= total_pages:
                break
        elif len(items) < page_size:
            break

        page += 1

    return rows


def _call_json(
    *,
    account: PagarmeAccount,
    path: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    base_url = account.base_url.rstrip("/")
    query = urlencode([(key, str(value)) for key, value in params.items() if value not in (None, "")])
    url = f"{base_url}{path}"
    if query:
        url = f"{url}?{query}"

    request = Request(
        url=url,
        headers={
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
            "Authorization": _build_basic_auth_header(account.secret_key),
        },
    )

    try:
        with urlopen(request, timeout=60) as response:
            payload = response.read().decode("utf-8")
            data = json.loads(payload)
    except HTTPError as error:
        response_text = error.read().decode("utf-8", errors="replace") if error.fp else ""
        raise PagarmeAPIError(
            _build_error_message(path=path, status_code=error.code, response_text=response_text)
        ) from error
    except URLError as error:
        raise PagarmeAPIError(f"Erro de conexao com o Pagar.me em {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise PagarmeAPIError(f"Resposta invalida do Pagar.me em {path}.") from error

    if isinstance(data, dict):
        return data
    raise PagarmeAPIError(f"Resposta inesperada do Pagar.me em {path}.")


def _build_basic_auth_header(secret_key: str) -> str:
    raw = f"{secret_key}:".encode("utf-8")
    token = base64.b64encode(raw).decode("ascii")
    return f"Basic {token}"


def _build_error_message(*, path: str, status_code: int, response_text: str) -> str:
    detail = response_text.strip()
    if not detail:
        return f"Erro HTTP {status_code} no Pagar.me em {path}."
    return f"Erro HTTP {status_code} no Pagar.me em {path}: {detail[:300]}"


def _extract_items(payload: dict[str, Any], items_keys: tuple[str, ...]) -> list[dict[str, Any]]:
    for key in items_keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    for key in ("data", "items", "orders", "charges", "payables"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _extract_total_pages(payload: dict[str, Any]) -> int | None:
    for candidate in (
        ("total_pages",),
        ("totalPages",),
        ("pages",),
        ("pagination", "total_pages"),
        ("meta", "total_pages"),
        ("meta", "pagination", "total_pages"),
    ):
        current: Any = payload
        for token in candidate:
            if not isinstance(current, dict):
                break
            current = current.get(token)
        else:
            try:
                total_pages = int(current)
            except (TypeError, ValueError):
                continue
            if total_pages > 0:
                return total_pages
    return None


def _parse_date(raw_value: str | None, fallback: date) -> date:
    text = str(raw_value or "").strip()
    if not text:
        return fallback

    for format_mask in (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
    ):
        try:
            return datetime.strptime(text, format_mask).date()
        except ValueError:
            continue

    raise ValueError(f"Data invalida para Pagar.me: {text}. Use DD/MM/AAAA ou AAAA-MM-DD.")


def _start_of_day_iso(value: date) -> str:
    return datetime.combine(value, time.min).replace(microsecond=0).isoformat() + "Z"


def _end_of_day_iso(value: date) -> str:
    return datetime.combine(value, time.max).replace(microsecond=0).isoformat() + "Z"


def _flatten_into(target: dict[str, object], prefix: str, value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            text_key = str(key or "").strip()
            if not text_key:
                continue
            next_prefix = f"{prefix}.{text_key}" if prefix else text_key
            _flatten_into(target, next_prefix, item)
        return
    if isinstance(value, list):
        target[prefix] = json.dumps(value, ensure_ascii=False)
        return
    target[prefix] = value
