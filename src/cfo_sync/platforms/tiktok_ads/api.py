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


logger = logging.getLogger(__name__)

BASE_URL = "https://business-api.tiktok.com"
MAX_PAGES_SAFETY = 500
DEFAULT_PAGE_SIZE = 100
RETRY_BACKOFF_SECONDS = (1.0, 3.0, 8.0)


class TikTokAdsAPIError(RuntimeError):
    pass


def normalize_period(start_date: str | None, end_date: str | None) -> tuple[str, str]:
    today = date.today()
    default_start = today.replace(day=1)
    start = _parse_date(start_date, default_start)
    end = _parse_date(end_date, today)

    if start > end:
        raise ValueError("Periodo invalido para TikTok Ads: data inicial maior que data final.")

    return start.isoformat(), end.isoformat()


def exchange_auth_code_for_access_token(
    app_id: str,
    secret: str,
    auth_code: str,
    redirect_uri: str | None = None,
) -> str:
    normalized_app_id = str(app_id or "").strip()
    normalized_secret = str(secret or "").strip()
    normalized_auth_code = str(auth_code or "").strip()
    if not normalized_app_id or not normalized_secret or not normalized_auth_code:
        raise ValueError("app_id, secret e auth_code sao obrigatorios para gerar access_token.")

    resolved_redirect_uri = str(redirect_uri or "").strip()
    endpoints = (
        "/open_api/v1.3/oauth2/access_token/",
        "/open_api/1.2/oauth2/access_token/",
    )
    last_error: Exception | None = None
    for endpoint in endpoints:
        try:
            payload: dict[str, object] = {
                "app_id": normalized_app_id,
                "secret": normalized_secret,
                "auth_code": normalized_auth_code,
            }
            if resolved_redirect_uri:
                payload["redirect_uri"] = resolved_redirect_uri
            response = _request_json_without_access_token(
                endpoint=endpoint,
                payload=payload,
                method="POST",
            )
            token = _extract_access_token(response)
            if token:
                return token
            raise TikTokAdsAPIError("Resposta OAuth sem access_token.")
        except (TikTokAdsAPIError, ValueError) as error:
            last_error = error
            continue

    if last_error is not None:
        raise TikTokAdsAPIError(f"Falha ao gerar access_token TikTok Ads: {last_error}") from last_error
    raise TikTokAdsAPIError("Falha ao gerar access_token TikTok Ads.")


def fetch_authorized_advertiser_ids(
    access_token: str,
    app_id: str | None = None,
    secret: str | None = None,
) -> list[str]:
    endpoints = (
        "/open_api/v1.3/oauth2/advertiser/get/",
        "/open_api/1.2/oauth2/advertiser/get/",
    )
    query_params: dict[str, object] = {}
    if str(app_id or "").strip():
        query_params["app_id"] = str(app_id).strip()
    if str(secret or "").strip():
        query_params["secret"] = str(secret).strip()

    last_error: Exception | None = None
    for endpoint in endpoints:
        try:
            response_payload = _request_resource(
                endpoint=endpoint,
                access_token=access_token,
                payload=query_params,
            )
            data = _extract_data_block(response_payload)
            return _extract_advertiser_ids(data)
        except TikTokAdsAPIError as error:
            last_error = error
            continue

    if last_error is not None:
        raise last_error
    return []


def fetch_advertiser_infos(
    access_token: str,
    advertiser_ids: list[str],
) -> list[dict[str, Any]]:
    normalized_ids = [str(item).strip() for item in advertiser_ids if str(item or "").strip()]
    if not normalized_ids:
        return []

    endpoints = (
        "/open_api/v1.3/advertiser/info/",
        "/open_api/1.2/advertiser/info/",
    )
    last_error: Exception | None = None
    for endpoint in endpoints:
        try:
            response_payload = _request_resource(
                endpoint=endpoint,
                access_token=access_token,
                payload={"advertiser_ids": normalized_ids},
            )
            data = _extract_data_block(response_payload)
            return _extract_rows(data)
        except TikTokAdsAPIError as error:
            last_error = error
            continue

    if last_error is not None:
        raise last_error
    return []


def fetch_paginated_rows(
    endpoint: str,
    access_token: str,
    advertiser_id: str,
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    if not str(access_token or "").strip():
        raise ValueError("Credenciais TikTok Ads incompletas: access_token ausente.")
    if not str(advertiser_id or "").strip():
        raise ValueError("advertiser_id TikTok Ads invalido.")

    rows: list[dict[str, Any]] = []
    page = 1
    while page <= MAX_PAGES_SAFETY:
        request_payload = _build_request_payload(
            advertiser_id=advertiser_id,
            page=page,
            page_size=DEFAULT_PAGE_SIZE,
            start_date=start_date,
            end_date=end_date,
        )
        response_payload = _request_with_payload_fallback(
            endpoint=endpoint,
            access_token=access_token,
            payload=request_payload,
        )
        data = _extract_data_block(response_payload)
        page_rows = _extract_rows(data)
        rows.extend(page_rows)

        if not _has_next_page(
            data=data,
            current_page=page,
            default_page_size=DEFAULT_PAGE_SIZE,
            received_count=len(page_rows),
        ):
            break
        page += 1

    return rows


def _request_with_payload_fallback(
    endpoint: str,
    access_token: str,
    payload: dict[str, object],
) -> dict[str, Any]:
    try:
        return _request_resource(
            endpoint=endpoint,
            access_token=access_token,
            payload=payload,
        )
    except TikTokAdsAPIError as error:
        if not _can_retry_without_period_params(error, payload):
            raise

    fallback_payload = {
        key: value
        for key, value in payload.items()
        if key not in {"start_date", "end_date"}
    }
    return _request_resource(
        endpoint=endpoint,
        access_token=access_token,
        payload=fallback_payload,
    )


def _request_resource(
    endpoint: str,
    access_token: str,
    payload: dict[str, object],
) -> dict[str, Any]:
    first_method = "POST" if "report/" in endpoint.lower() else "GET"
    methods = [first_method, "GET" if first_method == "POST" else "POST"]

    last_error: Exception | None = None
    for method in methods:
        try:
            return _request_json(
                endpoint=endpoint,
                access_token=access_token,
                payload=payload,
                method=method,
            )
        except TikTokAdsAPIError as error:
            last_error = error
            if not _can_retry_with_alternative_http_method(error):
                raise
            continue

    if last_error is not None:
        raise last_error
    raise TikTokAdsAPIError("Falha inesperada em chamada TikTok Ads API.")


def _request_json(
    endpoint: str,
    access_token: str,
    payload: dict[str, object],
    method: str,
) -> dict[str, Any]:
    url = _build_resource_url(endpoint)
    request_body: bytes | None = None
    headers = {
        "Access-Token": access_token,
        "Accept": "application/json",
    }

    if method == "GET":
        query = urlencode(
            {
                key: json.dumps(value, separators=(",", ":"))
                if isinstance(value, (dict, list))
                else str(value)
                for key, value in payload.items()
                if value not in (None, "")
            }
        )
        url = f"{url}?{query}" if query else url
    else:
        headers["Content-Type"] = "application/json"
        request_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    for attempt, backoff in enumerate((*RETRY_BACKOFF_SECONDS, None), start=1):
        request = Request(url=url, method=method, headers=headers, data=request_body)
        try:
            with urlopen(request, timeout=60) as response:
                raw_content = response.read().decode("utf-8")
                if not raw_content.strip():
                    return {}
                decoded = json.loads(raw_content)
                if not isinstance(decoded, dict):
                    raise TikTokAdsAPIError("Resposta invalida da API TikTok Ads.")
                _validate_business_error(decoded)
                return decoded
        except HTTPError as error:
            response_body = error.read().decode("utf-8", errors="ignore") if error.fp else ""
            if error.code in {408, 429, 500, 502, 503, 504} and backoff is not None:
                logger.warning(
                    "TikTok Ads HTTP %s (tentativa=%s). Novo retry em %.1fs.",
                    error.code,
                    attempt,
                    backoff,
                )
                time.sleep(backoff)
                continue
            raise TikTokAdsAPIError(
                f"Erro HTTP TikTok Ads (status={error.code}): {response_body[:500]}"
            ) from error
        except (URLError, TimeoutError, socket.timeout) as error:
            if backoff is not None:
                logger.warning(
                    "Erro de rede TikTok Ads (tentativa=%s). Novo retry em %.1fs. Erro=%s",
                    attempt,
                    backoff,
                    error,
                )
                time.sleep(backoff)
                continue
            raise TikTokAdsAPIError(f"Erro de conexao TikTok Ads: {error}") from error
        except json.JSONDecodeError as error:
            raise TikTokAdsAPIError("Resposta JSON invalida da TikTok Ads API.") from error

    raise TikTokAdsAPIError("Falha inesperada em chamada TikTok Ads API.")


def _request_json_without_access_token(
    endpoint: str,
    payload: dict[str, object],
    method: str = "POST",
) -> dict[str, Any]:
    url = _build_resource_url(endpoint)
    request_body: bytes | None = None
    headers = {
        "Accept": "application/json",
    }

    if method == "GET":
        query = urlencode(
            {
                key: json.dumps(value, separators=(",", ":"))
                if isinstance(value, (dict, list))
                else str(value)
                for key, value in payload.items()
                if value not in (None, "")
            }
        )
        url = f"{url}?{query}" if query else url
    else:
        headers["Content-Type"] = "application/json"
        request_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    for attempt, backoff in enumerate((*RETRY_BACKOFF_SECONDS, None), start=1):
        request = Request(url=url, method=method, headers=headers, data=request_body)
        try:
            with urlopen(request, timeout=60) as response:
                raw_content = response.read().decode("utf-8")
                if not raw_content.strip():
                    return {}
                decoded = json.loads(raw_content)
                if not isinstance(decoded, dict):
                    raise TikTokAdsAPIError("Resposta invalida da API TikTok Ads.")
                _validate_business_error(decoded)
                return decoded
        except HTTPError as error:
            response_body = error.read().decode("utf-8", errors="ignore") if error.fp else ""
            if error.code in {408, 429, 500, 502, 503, 504} and backoff is not None:
                logger.warning(
                    "TikTok Ads OAuth HTTP %s (tentativa=%s). Retry em %.1fs.",
                    error.code,
                    attempt,
                    backoff,
                )
                time.sleep(backoff)
                continue
            raise TikTokAdsAPIError(
                f"Erro HTTP TikTok Ads OAuth (status={error.code}): {response_body[:500]}"
            ) from error
        except (URLError, TimeoutError, socket.timeout) as error:
            if backoff is not None:
                logger.warning(
                    "Erro de rede TikTok Ads OAuth (tentativa=%s). Retry em %.1fs. Erro=%s",
                    attempt,
                    backoff,
                    error,
                )
                time.sleep(backoff)
                continue
            raise TikTokAdsAPIError(f"Erro de conexao TikTok Ads OAuth: {error}") from error
        except json.JSONDecodeError as error:
            raise TikTokAdsAPIError("Resposta JSON invalida da TikTok Ads API.") from error

    raise TikTokAdsAPIError("Falha inesperada em chamada TikTok Ads OAuth.")


def _build_resource_url(endpoint: str) -> str:
    base_url = str(os.getenv("TIKTOK_ADS_API_BASE_URL") or BASE_URL).strip().rstrip("/")
    normalized_endpoint = str(endpoint or "").strip()
    if not normalized_endpoint:
        raise ValueError("Endpoint TikTok Ads nao configurado no recurso.")

    if normalized_endpoint.startswith("http://") or normalized_endpoint.startswith("https://"):
        return normalized_endpoint

    if not normalized_endpoint.startswith("/"):
        normalized_endpoint = f"/{normalized_endpoint}"

    if normalized_endpoint.startswith("/open_api/"):
        return f"{base_url}{normalized_endpoint}"

    return f"{base_url}/open_api/v1.3{normalized_endpoint}"


def _validate_business_error(payload: dict[str, Any]) -> None:
    code = payload.get("code")
    if code in (None, 0, "0"):
        return

    message = str(payload.get("message") or payload.get("msg") or "Erro desconhecido")
    request_id = str(payload.get("request_id") or payload.get("requestId") or "").strip()
    request_suffix = f" request_id={request_id}" if request_id else ""
    raise TikTokAdsAPIError(f"TikTok Ads API error code={code}: {message}.{request_suffix}")


def _extract_data_block(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    return {}


def _extract_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = [
        data.get("list"),
        data.get("campaigns"),
        data.get("rows"),
        data.get("items"),
        data.get("data"),
    ]
    for candidate in candidates:
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
    return []


def _extract_advertiser_ids(data: dict[str, Any]) -> list[str]:
    possible_lists: list[list[Any]] = []
    for key in ("list", "advertisers", "items", "data"):
        value = data.get(key)
        if isinstance(value, list):
            possible_lists.append(value)

    advertiser_ids: list[str] = []
    for rows in possible_lists:
        for item in rows:
            if isinstance(item, dict):
                candidate = item.get("advertiser_id") or item.get("id")
            else:
                candidate = item
            normalized = "".join(ch for ch in str(candidate or "") if ch.isdigit())
            if normalized and normalized not in advertiser_ids:
                advertiser_ids.append(normalized)

    return advertiser_ids


def _extract_access_token(payload: dict[str, Any]) -> str:
    top_level_token = str(payload.get("access_token") or "").strip()
    if top_level_token:
        return top_level_token

    data = payload.get("data")
    if isinstance(data, dict):
        nested_token = str(data.get("access_token") or "").strip()
        if nested_token:
            return nested_token

    return ""


def _has_next_page(
    data: dict[str, Any],
    current_page: int,
    default_page_size: int,
    received_count: int,
) -> bool:
    page_info = data.get("page_info")
    if isinstance(page_info, dict):
        current = _to_int(page_info.get("page") or page_info.get("page_num")) or current_page
        total_pages = _to_int(page_info.get("total_page") or page_info.get("total_pages"))
        if total_pages > 0:
            return current < total_pages

        total_rows = _to_int(page_info.get("total_number") or page_info.get("total"))
        page_size = _to_int(page_info.get("page_size") or page_info.get("size")) or default_page_size
        if total_rows > 0 and page_size > 0:
            return current * page_size < total_rows

        raw_has_next = page_info.get("has_next_page")
        if isinstance(raw_has_next, bool):
            return raw_has_next

    raw_has_more = data.get("has_more")
    if isinstance(raw_has_more, bool):
        return raw_has_more

    return received_count >= default_page_size


def _build_request_payload(
    advertiser_id: str,
    page: int,
    page_size: int,
    start_date: str,
    end_date: str,
) -> dict[str, object]:
    return {
        "advertiser_id": advertiser_id,
        "page": page,
        "page_size": page_size,
        # Alguns endpoints ignoram esses parametros; manter no payload padrao simplifica a integracao.
        "start_date": start_date,
        "end_date": end_date,
    }


def _parse_date(raw_value: str | None, default_value: date) -> date:
    if raw_value is None or str(raw_value).strip() == "":
        return default_value
    return date.fromisoformat(str(raw_value).strip())


def _to_int(raw_value: object) -> int:
    if raw_value in (None, ""):
        return 0
    if isinstance(raw_value, bool):
        return int(raw_value)
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, float):
        return int(raw_value)
    try:
        return int(float(str(raw_value).strip()))
    except ValueError:
        return 0


def _can_retry_with_alternative_http_method(error: Exception) -> bool:
    text = str(error).upper()
    return any(token in text for token in ("METHOD", "405", "NOT ALLOWED"))


def _can_retry_without_period_params(
    error: Exception,
    payload: dict[str, object],
) -> bool:
    if "start_date" not in payload and "end_date" not in payload:
        return False

    text = str(error).upper()
    has_param_hint = any(token in text for token in ("PARAM", "INVALID", "UNKNOWN", "UNSUPPORTED"))
    has_date_hint = any(token in text for token in ("START_DATE", "END_DATE", "DATE"))
    return has_param_hint and has_date_hint
