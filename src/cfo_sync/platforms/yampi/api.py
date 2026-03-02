from __future__ import annotations

import json
import socket
import time
from datetime import date, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from cfo_sync.platforms.yampi.credentials import YampiAliasCredential


BASE_URL = "https://api.dooki.com.br/v2/"
DEFAULT_PAGE_SIZE = 100
MAX_PAGES_SAFETY = 2000
RETRY_BACKOFF_SECONDS = (1.0, 3.0, 8.0)


class YampiAPIError(RuntimeError):
    pass


def fetch_orders_for_period(
    credential: YampiAliasCredential,
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if start > end:
        raise ValueError("Data inicial nao pode ser maior que a data final.")

    unique_orders: dict[str, dict[str, Any]] = {}
    current = start
    while current <= end:
        month_end = _month_last_day(current)
        window_end = month_end if month_end <= end else end
        window_orders = _fetch_orders_window(
            credential=credential,
            start_date=current.isoformat(),
            end_date=window_end.isoformat(),
        )
        for order in window_orders:
            order_id = str(order.get("id") or "")
            if order_id and order_id not in unique_orders:
                unique_orders[order_id] = order
        current = window_end + timedelta(days=1)

    return list(unique_orders.values())


def fetch_orders_by_number(
    credential: YampiAliasCredential,
    order_number: str,
) -> list[dict[str, Any]]:
    number = str(order_number).strip()
    if not number:
        return []

    strategies: list[dict[str, str]] = [
        {"number": number},
        {"id": number},
        {"search": number},
    ]

    for strategy in strategies:
        try:
            rows = _fetch_orders_by_params(credential=credential, extra_params=strategy)
            if rows:
                return rows
        except YampiAPIError:
            continue

    return []


def _fetch_orders_window(
    credential: YampiAliasCredential,
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    limit_error: YampiAPIError | None = None
    try:
        return _fetch_orders_window_no_split(
            credential=credential,
            start_date=start_date,
            end_date=end_date,
        )
    except YampiAPIError as error:
        if "Maximum limit is 10000" not in str(error):
            raise
        limit_error = error

    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if start >= end:
        if limit_error is not None:
            raise limit_error
        raise YampiAPIError("Falha ao coletar pedidos da Yampi.")

    midpoint = start + (end - start) // 2
    left_orders = _fetch_orders_window(
        credential=credential,
        start_date=start.isoformat(),
        end_date=midpoint.isoformat(),
    )
    right_orders = _fetch_orders_window(
        credential=credential,
        start_date=(midpoint + timedelta(days=1)).isoformat(),
        end_date=end.isoformat(),
    )

    unique_orders: dict[str, dict[str, Any]] = {}
    for order in (*left_orders, *right_orders):
        order_id = str(order.get("id") or "")
        if order_id and order_id not in unique_orders:
            unique_orders[order_id] = order
    return list(unique_orders.values())


def _fetch_orders_by_params(
    credential: YampiAliasCredential,
    extra_params: dict[str, str],
) -> list[dict[str, Any]]:
    page = 1
    total_pages = 1
    unique_orders: dict[str, dict[str, Any]] = {}

    while page <= total_pages and page <= MAX_PAGES_SAFETY:
        params: dict[str, str] = {
            "page": str(page),
            "limit": str(DEFAULT_PAGE_SIZE),
            "include": "items",
            **extra_params,
        }

        payload = _request_orders(
            alias=credential.alias,
            user_token=credential.user_token,
            user_secret_key=credential.user_secret_key,
            params=params,
        )

        for order in payload.get("data", []):
            order_id = str(order.get("id") or "")
            if not order_id:
                continue
            if order_id not in unique_orders:
                unique_orders[order_id] = order

        pagination = (payload.get("meta") or {}).get("pagination") or {}
        total_pages = int(pagination.get("total_pages") or 1)
        page += 1
        time.sleep(0.2)

    return list(unique_orders.values())


def _fetch_orders_window_no_split(
    credential: YampiAliasCredential,
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    page = 1
    total_pages = 1
    unique_orders: dict[str, dict[str, Any]] = {}

    while page <= total_pages and page <= MAX_PAGES_SAFETY:
        params: dict[str, str] = {
            "page": str(page),
            "limit": str(DEFAULT_PAGE_SIZE),
            "date": f"created_at:{start_date}|{end_date}",
            "include": "items",
        }

        payload = _request_orders(
            alias=credential.alias,
            user_token=credential.user_token,
            user_secret_key=credential.user_secret_key,
            params=params,
        )

        for order in payload.get("data", []):
            order_id = str(order.get("id") or "")
            if not order_id:
                continue
            if order_id not in unique_orders:
                unique_orders[order_id] = order

        pagination = (payload.get("meta") or {}).get("pagination") or {}
        total_pages = int(pagination.get("total_pages") or 1)

        page += 1
        time.sleep(0.2)

    return list(unique_orders.values())


def _month_last_day(day: date) -> date:
    if day.month == 12:
        return date(day.year, 12, 31)
    first_next_month = date(day.year, day.month + 1, 1)
    return first_next_month - timedelta(days=1)


def _request_orders(
    alias: str,
    user_token: str,
    user_secret_key: str,
    params: dict[str, str],
) -> dict[str, Any]:
    query = urlencode(params)
    url = f"{BASE_URL}{alias}/orders?{query}"

    headers = {
        "User-Token": user_token,
        "User-Secret-Key": user_secret_key,
        "Content-Type": "application/json",
    }

    for _attempt, backoff in enumerate((*RETRY_BACKOFF_SECONDS, None), start=1):
        request = Request(url=url, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=30) as response:
                content = response.read().decode("utf-8")
                return json.loads(content)
        except HTTPError as error:
            body = error.read().decode("utf-8", errors="ignore") if error.fp else ""
            should_retry = error.code in {429, 500, 502, 503, 504}
            if should_retry and backoff is not None:
                time.sleep(backoff)
                continue
            raise YampiAPIError(
                f"Erro HTTP na Yampi (alias={alias}, status={error.code}): {body[:300]}"
            ) from error
        except (URLError, TimeoutError, socket.timeout) as error:
            if backoff is not None:
                time.sleep(backoff)
                continue
            raise YampiAPIError(f"Erro de conexao na Yampi (alias={alias}): {error}") from error
        except json.JSONDecodeError as error:
            raise YampiAPIError(f"Resposta invalida da Yampi (alias={alias})") from error

    raise YampiAPIError(f"Falha inesperada ao chamar Yampi (alias={alias})")


def normalize_period(start_date: str | None, end_date: str | None) -> tuple[str, str]:
    today = date.today()
    default_start = today.replace(day=1)

    start = _parse_date(start_date, default_start)
    end = _parse_date(end_date, today)

    if start > end:
        raise ValueError("Data inicial nao pode ser maior que a data final.")

    return start.isoformat(), end.isoformat()


def _parse_date(raw_value: str | None, default_value: date) -> date:
    if raw_value is None or str(raw_value).strip() == "":
        return default_value
    return date.fromisoformat(str(raw_value))
