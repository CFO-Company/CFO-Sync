from __future__ import annotations

import json
import logging
import os
import socket
import time
from datetime import date
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from cfo_sync.platforms.google_ads.credentials import GoogleAdsAuth


class GoogleAdsAPIError(RuntimeError):
    pass


RETRY_BACKOFF_SECONDS = (1.0, 3.0, 8.0)
OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
DEFAULT_API_VERSION = "v22"
DEFAULT_API_VERSION_CANDIDATES = ("v22", "v21", "v20")
logger = logging.getLogger(__name__)


def normalize_period(
    start_date: str | None,
    end_date: str | None,
) -> tuple[str, str]:
    today = date.today()
    default_start = today.replace(day=1)
    start = _parse_date(start_date, default_start)
    end = _parse_date(end_date, today)

    if start > end:
        raise ValueError("Periodo invalido para Google ADS: data inicial maior que data final.")

    return start.isoformat(), end.isoformat()


def search_stream(
    auth: GoogleAdsAuth,
    customer_id: str,
    query: str,
) -> list[dict[str, Any]]:
    _validate_auth(auth)
    resolved_customer_id = _normalize_customer_id(customer_id)
    if not resolved_customer_id:
        raise ValueError("customer_id Google Ads invalido.")

    access_token = fetch_access_token(auth)
    request_body = json.dumps({"query": query}).encode("utf-8")
    headers = _google_ads_headers(auth=auth, access_token=access_token)

    candidates = _candidate_api_versions()
    last_error: Exception | None = None
    for index, version in enumerate(candidates):
        try:
            payload = _request_json(
                url=f"{_api_base_url(version)}/customers/{resolved_customer_id}/googleAds:searchStream",
                method="POST",
                headers=headers,
                body=request_body,
            )
            return _extract_stream_results(payload)
        except GoogleAdsAPIError as error:
            last_error = error
            if _is_unimplemented_error(error) and index < len(candidates) - 1:
                logger.warning(
                    "Google Ads SearchStream indisponivel em %s para customer_id=%s. Tentando proxima versão.",
                    version,
                    resolved_customer_id,
                )
                continue
            raise

    if last_error is not None:
        raise last_error
    return []


def fetch_access_token(auth: GoogleAdsAuth) -> str:
    _validate_auth(auth)
    body = urlencode(
        {
            "client_id": auth.client_id,
            "client_secret": auth.client_secret,
            "refresh_token": auth.refresh_token,
            "grant_type": "refresh_token",
        }
    ).encode("utf-8")

    payload = _request_json(
        url=OAUTH_TOKEN_URL,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=body,
    )

    if not isinstance(payload, dict):
        raise GoogleAdsAPIError("Resposta OAuth invalida do Google Ads.")

    access_token = str(payload.get("access_token") or "").strip()
    if not access_token:
        raise GoogleAdsAPIError("Resposta OAuth invalida do Google Ads: access_token ausente.")
    return access_token


def _request_json(
    url: str,
    method: str,
    headers: dict[str, str],
    body: bytes | None = None,
) -> dict[str, Any] | list[Any]:
    for attempt, backoff in enumerate((*RETRY_BACKOFF_SECONDS, None), start=1):
        request = Request(url=url, method=method, headers=headers, data=body)
        try:
            with urlopen(request, timeout=60) as response:
                content = response.read().decode("utf-8")
                if not content.strip():
                    return {}
                return json.loads(content)
        except HTTPError as error:
            response_body = error.read().decode("utf-8", errors="ignore") if error.fp else ""
            if error.code in {408, 429, 500, 502, 503, 504} and backoff is not None:
                logger.warning(
                    "Google Ads HTTP %s (tentativa=%s). Novo retry em %.1fs.",
                    error.code,
                    attempt,
                    backoff,
                )
                time.sleep(backoff)
                continue
            raise GoogleAdsAPIError(
                f"Erro HTTP Google Ads (status={error.code}): {response_body[:500]}"
            ) from error
        except (URLError, TimeoutError, socket.timeout) as error:
            if backoff is not None:
                logger.warning(
                    "Erro de rede Google Ads (tentativa=%s). Novo retry em %.1fs. Erro=%s",
                    attempt,
                    backoff,
                    error,
                )
                time.sleep(backoff)
                continue
            raise GoogleAdsAPIError(f"Erro de conexao Google Ads: {error}") from error
        except json.JSONDecodeError as error:
            raise GoogleAdsAPIError("Resposta JSON invalida da Google Ads API.") from error

    raise GoogleAdsAPIError("Falha inesperada em chamada Google Ads API.")


def _extract_stream_results(payload: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    chunks = payload if isinstance(payload, list) else [payload]
    rows: list[dict[str, Any]] = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        results = chunk.get("results") or []
        if isinstance(results, list):
            rows.extend([item for item in results if isinstance(item, dict)])
    return rows


def _google_ads_headers(auth: GoogleAdsAuth, access_token: str) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "developer-token": auth.developer_token,
        "Content-Type": "application/json",
    }
    if auth.login_customer_id:
        headers["login-customer-id"] = _normalize_customer_id(auth.login_customer_id)
    return headers


def _validate_auth(auth: GoogleAdsAuth) -> None:
    missing = [
        field_name
        for field_name, value in (
            ("developer_token", auth.developer_token),
            ("client_id", auth.client_id),
            ("client_secret", auth.client_secret),
            ("refresh_token", auth.refresh_token),
        )
        if not str(value or "").strip()
    ]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(
            f"Credenciais Google Ads incompletas. Campos obrigatorios ausentes: {joined}"
        )


def _api_base_url(version: str) -> str:
    return f"https://googleads.googleapis.com/{_normalize_version(version)}"


def _normalize_customer_id(customer_id: str) -> str:
    return "".join(ch for ch in str(customer_id) if ch.isdigit())


def _parse_date(raw_value: str | None, fallback: date) -> date:
    if raw_value is None or str(raw_value).strip() == "":
        return fallback
    return date.fromisoformat(str(raw_value).strip())


def _candidate_api_versions() -> list[str]:
    configured_version = str(os.getenv("GOOGLE_ADS_API_VERSION") or "").strip()
    if configured_version:
        return [_normalize_version(configured_version)]

    configured_fallbacks = str(os.getenv("GOOGLE_ADS_API_VERSION_FALLBACKS") or "").strip()
    if configured_fallbacks:
        parts = [item.strip() for item in configured_fallbacks.split(",") if item.strip()]
        if parts:
            return [_normalize_version(part) for part in parts]

    return [_normalize_version(version) for version in DEFAULT_API_VERSION_CANDIDATES]


def _normalize_version(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        text = DEFAULT_API_VERSION
    return text if text.startswith("v") else f"v{text}"


def _is_unimplemented_error(error: Exception) -> bool:
    message = str(error).upper()
    has_unimplemented = "UNIMPLEMENTED" in message
    has_501 = "STATUS=501" in message or "\"CODE\": 501" in message or "CODE: 501" in message
    return has_unimplemented or has_501
