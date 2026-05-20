from __future__ import annotations

import hashlib
import hmac
import json
import os
import socket
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date
from typing import Any, Callable, Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from cfo_sync.platforms.meta_ads.credentials import MetaAdsAuth


BASE_URL = "https://graph.facebook.com/v20.0"
MAX_PAGES_SAFETY = 2000
RETRY_BACKOFF_SECONDS = tuple(
    float(value)
    for value in os.getenv("CFO_SYNC_META_ADS_RETRY_BACKOFF_SECONDS", "30,90,180").split(",")
    if value.strip()
)
MAX_CONCURRENT_REQUESTS = max(1, int(os.getenv("CFO_SYNC_META_ADS_MAX_CONCURRENT_REQUESTS", "1")))
USAGE_HEADER_NAMES = (
    "x-app-usage",
    "x-ad-account-usage",
    "x-business-use-case-usage",
)
_REQUEST_SEMAPHORE = threading.BoundedSemaphore(MAX_CONCURRENT_REQUESTS)
_LOG_CALLBACK: ContextVar[Callable[[str], None] | None] = ContextVar(
    "meta_ads_api_log_callback",
    default=None,
)


class MetaAdsAPIError(RuntimeError):
    pass


@contextmanager
def meta_ads_api_logging(log: Callable[[str], None] | None) -> Iterator[None]:
    token = _LOG_CALLBACK.set(log)
    try:
        yield
    finally:
        _LOG_CALLBACK.reset(token)


def iter_paginated(
    path: str,
    auth: MetaAdsAuth,
    params: dict[str, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    next_path_or_url: str | None = path
    page = 0
    first_request = True

    while next_path_or_url and page < MAX_PAGES_SAFETY:
        payload = _request_json(
            path_or_url=next_path_or_url,
            auth=auth,
            params=params if first_request else None,
        )
        first_request = False
        rows.extend([item for item in payload.get("data", []) if isinstance(item, dict)])
        next_path_or_url = ((payload.get("paging") or {}).get("next")) or None
        page += 1

    return rows


def normalize_period(start_date: str | None, end_date: str | None) -> tuple[str, str]:
    today = date.today()
    default_start = today.replace(day=1)
    start = _parse_date(start_date, default_start)
    end = _parse_date(end_date, today)

    if start > end:
        raise ValueError("Data inicial nao pode ser maior que data final.")

    return start.isoformat(), end.isoformat()


def _request_json(
    path_or_url: str,
    auth: MetaAdsAuth,
    params: dict[str, str] | None,
) -> dict[str, Any]:
    appsecret_proof = _build_appsecret_proof(auth.access_token, auth.app_secret)
    url = _build_url(path_or_url, auth.access_token, appsecret_proof, params)

    for attempt, backoff in enumerate((*RETRY_BACKOFF_SECONDS, None), start=1):
        request = Request(url=url, method="GET")
        try:
            with _REQUEST_SEMAPHORE:
                with urlopen(request, timeout=30) as response:
                    _log_usage_headers(response.headers)
                    return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            body = error.read().decode("utf-8", errors="ignore") if error.fp else ""
            _log_usage_headers(error.headers)
            if _is_retryable_http_error(error=error, body=body) and backoff is not None:
                sleep_seconds = _retry_after_seconds(error) or backoff
                _log_api_event(
                    "Meta Ads rate limit/transient error: "
                    f"status={error.code} tentativa={attempt} aguardando={sleep_seconds:g}s"
                )
                time.sleep(sleep_seconds)
                continue
            raise MetaAdsAPIError(
                f"Erro HTTP no Meta Ads (status={error.code}): {body[:300]}"
            ) from error
        except (URLError, TimeoutError, socket.timeout) as error:
            if backoff is not None:
                time.sleep(backoff)
                continue
            raise MetaAdsAPIError(f"Erro de conexao no Meta Ads: {error}") from error
        except json.JSONDecodeError as error:
            raise MetaAdsAPIError("Resposta invalida da API Meta Ads.") from error

    raise MetaAdsAPIError("Falha inesperada ao chamar a API Meta Ads.")


def _is_retryable_http_error(error: HTTPError, body: str) -> bool:
    if error.code in {429, 500, 502, 503, 504}:
        return True
    if error.code != 403:
        return False

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return False

    meta_error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(meta_error, dict):
        return False

    return bool(meta_error.get("is_transient")) or meta_error.get("code") == 4


def _retry_after_seconds(error: HTTPError) -> float | None:
    raw_value = error.headers.get("Retry-After") if error.headers else None
    if raw_value is None:
        return None
    try:
        value = float(raw_value)
    except ValueError:
        return None
    return value if value > 0 else None


def _log_usage_headers(headers: Any) -> None:
    if not headers:
        return

    parts: list[str] = []
    for header_name in USAGE_HEADER_NAMES:
        value = headers.get(header_name)
        if value:
            parts.append(f"{header_name}={value}")
    if parts:
        _log_api_event("Meta Ads usage headers: " + " ".join(parts))


def _log_api_event(message: str) -> None:
    log = _LOG_CALLBACK.get()
    if log is not None:
        log(message)


def _build_url(
    path_or_url: str,
    access_token: str,
    appsecret_proof: str,
    params: dict[str, str] | None,
) -> str:
    base = path_or_url if path_or_url.startswith("http") else f"{BASE_URL}{path_or_url}"
    parsed = urlparse(base)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))

    if params:
        query.update(params)

    query["access_token"] = access_token
    query["appsecret_proof"] = appsecret_proof

    return urlunparse(parsed._replace(query=urlencode(query)))


def _build_appsecret_proof(access_token: str, app_secret: str) -> str:
    return hmac.new(
        app_secret.encode("utf-8"),
        access_token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _parse_date(raw_value: str | None, default_value: date) -> date:
    if raw_value is None or str(raw_value).strip() == "":
        return default_value
    return date.fromisoformat(str(raw_value))
