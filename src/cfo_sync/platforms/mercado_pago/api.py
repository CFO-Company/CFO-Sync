from __future__ import annotations

import json
from datetime import date, datetime, time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from cfo_sync.platforms.mercado_pago.credentials import MercadoPagoAccount


DEFAULT_PAGE_SIZE = 100
USER_AGENT = "CFO-Sync/1.0"


class MercadoPagoAPIError(RuntimeError):
    pass


def normalize_period(start_date: str | None, end_date: str | None) -> tuple[str, str]:
    today = date.today()
    start = _parse_date(start_date, today.replace(day=1))
    end = _parse_date(end_date, today)
    if start > end:
        raise ValueError("Data inicial nao pode ser maior que data final.")
    return start.isoformat(), end.isoformat()


def list_payments(
    account: MercadoPagoAccount,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    since, until = normalize_period(start_date, end_date)
    return _paginate(
        account=account,
        path="/v1/payments/search",
        params={
            "sort": "date_created",
            "criteria": "desc",
            "range": "date_created",
            "begin_date": _to_api_datetime(since, end_of_day=False),
            "end_date": _to_api_datetime(until, end_of_day=True),
            "offset": 0,
            "limit": DEFAULT_PAGE_SIZE,
        },
    )


def get_payment(account: MercadoPagoAccount, payment_id: str) -> dict[str, Any]:
    return _call_json(account=account, path=f"/v1/payments/{payment_id}", params={})


def flatten_record(value: dict[str, Any]) -> dict[str, object]:
    flattened: dict[str, object] = {}
    _flatten_into(flattened, "", value)
    return flattened


def _paginate(
    *,
    account: MercadoPagoAccount,
    path: str,
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    offset = max(0, int(params.get("offset") or 0))
    limit = max(1, int(params.get("limit") or DEFAULT_PAGE_SIZE))
    rows: list[dict[str, Any]] = []

    while True:
        request_params = dict(params)
        request_params["offset"] = offset
        request_params["limit"] = limit
        response = _call_json(account=account, path=path, params=request_params)
        items = _extract_items(response)
        if not items:
            break

        rows.extend(items)
        paging = response.get("paging")
        total = _to_int(paging.get("total") if isinstance(paging, dict) else response.get("total"))
        if total is not None:
            if offset + len(items) >= total:
                break
        elif len(items) < limit:
            break

        offset += limit

    return rows


def _call_json(
    *,
    account: MercadoPagoAccount,
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
            "Authorization": f"Bearer {account.access_token}",
        },
    )

    try:
        with urlopen(request, timeout=60) as response:
            payload = response.read().decode("utf-8")
            data = json.loads(payload)
    except HTTPError as error:
        response_text = error.read().decode("utf-8", errors="replace") if error.fp else ""
        raise MercadoPagoAPIError(
            _build_error_message(path=path, status_code=error.code, response_text=response_text)
        ) from error
    except URLError as error:
        raise MercadoPagoAPIError(f"Erro de conexao com o Mercado Pago em {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise MercadoPagoAPIError(f"Resposta invalida do Mercado Pago em {path}.") from error

    if isinstance(data, dict):
        return data
    raise MercadoPagoAPIError(f"Resposta inesperada do Mercado Pago em {path}.")


def _extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("results", "data", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _build_error_message(*, path: str, status_code: int, response_text: str) -> str:
    detail = response_text.strip()
    if not detail:
        return f"Erro HTTP {status_code} no Mercado Pago em {path}."
    return f"Erro HTTP {status_code} no Mercado Pago em {path}: {detail[:300]}"


def _parse_date(raw_value: str | None, fallback: date) -> date:
    text = str(raw_value or "").strip()
    if not text:
        return fallback
    try:
        return date.fromisoformat(text)
    except ValueError:
        return fallback


def _to_api_datetime(raw_date: str, *, end_of_day: bool) -> str:
    parsed = date.fromisoformat(raw_date)
    parsed_time = time.max.replace(microsecond=0) if end_of_day else time.min
    return f"{datetime.combine(parsed, parsed_time).isoformat()}.000-03:00"


def _to_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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
