from __future__ import annotations

import json
import socket
import time
from datetime import date
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = "https://api.bling.com.br/Api/v3"
DEFAULT_PAGE_SIZE = 100
MAX_PAGES_SAFETY = 500
REQUEST_INTERVAL_SECONDS = 0.36
RETRY_BACKOFF_SECONDS = (1.0, 3.0, 8.0)


class BlingAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def normalize_period(start_date: str | None, end_date: str | None) -> tuple[str, str]:
    today = date.today()
    default_start = today.replace(day=1)
    start = _parse_date(start_date, default_start)
    end = _parse_date(end_date, today)
    if start > end:
        raise ValueError("Periodo invalido para Bling: data inicial maior que data final.")
    return start.isoformat(), end.isoformat()


def fetch_paginated_rows(
    *,
    endpoint: str,
    access_token: str,
    start_date: str | None,
    end_date: str | None,
    extra_params: dict[str, object] | None = None,
) -> list[dict[str, Any]]:
    path, fixed_params = _resolve_endpoint(endpoint)
    period_start, period_end = normalize_period(start_date, end_date)
    period_params = _period_params_for_path(
        path=path,
        start_date=period_start,
        end_date=period_end,
    )
    params = {**fixed_params, **period_params, **(extra_params or {})}

    try:
        return _fetch_pages(path=path, access_token=access_token, params=params)
    except BlingAPIError as error:
        if period_params and error.status_code == 400:
            fallback_params = {**fixed_params, **(extra_params or {})}
            return _fetch_pages(path=path, access_token=access_token, params=fallback_params)
        raise


def _fetch_pages(
    *,
    path: str,
    access_token: str,
    params: dict[str, object],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = 1
    while page <= MAX_PAGES_SAFETY:
        page_params = dict(params)
        page_params.setdefault("limite", DEFAULT_PAGE_SIZE)
        page_params["pagina"] = page
        payload = request_json(path=path, access_token=access_token, params=page_params)
        page_rows = _extract_rows(payload)
        rows.extend(page_rows)
        if len(page_rows) < int(page_params["limite"]):
            break
        page += 1
        time.sleep(REQUEST_INTERVAL_SECONDS)
    return rows


def request_json(
    *,
    path: str,
    access_token: str,
    params: dict[str, object] | None = None,
) -> dict[str, Any]:
    token = str(access_token or "").strip()
    if not token:
        raise ValueError("access_token Bling ausente.")

    url = _build_url(path=path, params=params or {})
    for backoff in (*RETRY_BACKOFF_SECONDS, None):
        request = Request(
            url=url,
            method="GET",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=45) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            error_body = error.read().decode("utf-8", errors="ignore") if error.fp else ""
            if error.code in {429, 500, 502, 503, 504} and backoff is not None:
                time.sleep(backoff)
                continue
            raise BlingAPIError(
                f"Falha na API Bling (status={error.code}): {error_body[:300]}",
                status_code=error.code,
            ) from error
        except (URLError, TimeoutError, socket.timeout) as error:
            if backoff is not None:
                time.sleep(backoff)
                continue
            raise BlingAPIError(f"Falha de conexao na API Bling: {error}") from error
        except json.JSONDecodeError as error:
            raise BlingAPIError("Resposta invalida da API Bling.") from error

        if not isinstance(payload, dict):
            raise BlingAPIError("Resposta invalida da API Bling: esperado objeto JSON.")
        return payload

    raise BlingAPIError("Falha inesperada na API Bling.")


def flatten_record(value: dict[str, Any]) -> dict[str, object]:
    flattened: dict[str, object] = {}
    _flatten_into(flattened, "", value)
    return flattened


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


def _extract_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _period_params_for_path(path: str, start_date: str, end_date: str) -> dict[str, str]:
    normalized = path.strip("/").casefold()
    if normalized in {"pedidos/vendas", "pedidos/compras"}:
        return {"dataInicial": start_date, "dataFinal": end_date}
    if normalized in {"produtos", "contatos"}:
        return {"dataAlteracaoInicial": start_date, "dataAlteracaoFinal": end_date}
    if normalized in {"nfe", "nfce"}:
        return {"dataEmissaoInicial": start_date, "dataEmissaoFinal": end_date}
    if normalized in {"contas/receber", "contas/pagar"}:
        return {"dataVencimentoInicial": start_date, "dataVencimentoFinal": end_date}
    return {}


def _resolve_endpoint(endpoint: str) -> tuple[str, dict[str, object]]:
    raw = str(endpoint or "").strip()
    if not raw:
        raise ValueError("Endpoint Bling nao informado no recurso.")
    if "?" not in raw:
        return raw.strip("/"), {}
    path, query = raw.split("?", 1)
    params: dict[str, object] = {}
    for pair in query.split("&"):
        if not pair:
            continue
        key, _, value = pair.partition("=")
        if key:
            params[key] = value
    return path.strip("/"), params


def _build_url(*, path: str, params: dict[str, object]) -> str:
    cleaned_params = {
        key: value
        for key, value in params.items()
        if value is not None and str(value).strip() != ""
    }
    query = urlencode(cleaned_params, doseq=True)
    url = f"{BASE_URL}/{path.strip('/')}"
    if query:
        return f"{url}?{query}"
    return url


def _parse_date(raw_value: str | None, default: date) -> date:
    text = str(raw_value or "").strip()
    if not text:
        return default
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return default
