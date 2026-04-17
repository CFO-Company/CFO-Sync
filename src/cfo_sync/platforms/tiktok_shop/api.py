from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import socket
import time
from datetime import date, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlparse
from urllib.request import Request, urlopen

from cfo_sync.platforms.tiktok_shop.credentials import TikTokShopAuth


logger = logging.getLogger(__name__)

BASE_URL = "https://open-api.tiktokglobalshop.com"
AUTH_BASE_URL = "https://auth.tiktok-shops.com"
MAX_PAGES_SAFETY = 500
DEFAULT_PAGE_SIZE = 100
RETRY_BACKOFF_SECONDS = (1.0, 3.0, 8.0)


class TikTokShopAPIError(RuntimeError):
    pass


def normalize_period(start_date: str | None, end_date: str | None) -> tuple[str, str]:
    today = date.today()
    default_start = today.replace(day=1)
    start = _parse_date(start_date, default_start)
    end = _parse_date(end_date, today)

    if start > end:
        raise ValueError("Periodo invalido para TikTok Shop: data inicial maior que data final.")

    return start.isoformat(), end.isoformat()


def exchange_auth_code_for_access_token(
    *,
    app_key: str,
    app_secret: str,
    auth_code: str,
    redirect_uri: str | None = None,
) -> dict[str, Any]:
    normalized_key = str(app_key or "").strip()
    normalized_secret = str(app_secret or "").strip()
    normalized_code = str(auth_code or "").strip()
    if not normalized_key or not normalized_secret or not normalized_code:
        raise ValueError("app_key, app_secret e auth_code sao obrigatorios para OAuth TikTok Shop.")

    resolved_redirect_uri = str(redirect_uri or "").strip()
    payload: dict[str, object] = {
        "app_key": normalized_key,
        "app_secret": normalized_secret,
        "auth_code": normalized_code,
        "grant_type": "authorized_code",
    }
    if resolved_redirect_uri:
        payload["redirect_uri"] = resolved_redirect_uri

    endpoints = (
        "/api/v2/token/get",
        "/api/v2/token/getAccessToken",
        "/api/token/getAccessToken",
    )
    last_error: Exception | None = None
    for endpoint in endpoints:
        try:
            response = _request_auth_json(endpoint=endpoint, payload=payload)
            return _extract_token_bundle(response)
        except (TikTokShopAPIError, ValueError) as error:
            last_error = error
            continue

    if last_error is not None:
        raise TikTokShopAPIError(f"Falha ao gerar token TikTok Shop: {last_error}") from last_error
    raise TikTokShopAPIError("Falha ao gerar token TikTok Shop.")


def refresh_access_token(
    *,
    app_key: str,
    app_secret: str,
    refresh_token: str,
) -> dict[str, Any]:
    normalized_key = str(app_key or "").strip()
    normalized_secret = str(app_secret or "").strip()
    normalized_refresh = str(refresh_token or "").strip()
    if not normalized_key or not normalized_secret or not normalized_refresh:
        raise ValueError("app_key, app_secret e refresh_token sao obrigatorios para refresh TikTok Shop.")

    payload: dict[str, object] = {
        "app_key": normalized_key,
        "app_secret": normalized_secret,
        "refresh_token": normalized_refresh,
        "grant_type": "refresh_token",
    }
    endpoints = (
        "/api/v2/token/refresh",
        "/api/v2/token/refreshToken",
        "/api/token/refreshToken",
    )
    last_error: Exception | None = None
    for endpoint in endpoints:
        try:
            response = _request_auth_json(endpoint=endpoint, payload=payload)
            return _extract_token_bundle(response)
        except (TikTokShopAPIError, ValueError) as error:
            last_error = error
            continue

    if last_error is not None:
        raise TikTokShopAPIError(f"Falha ao renovar token TikTok Shop: {last_error}") from last_error
    raise TikTokShopAPIError("Falha ao renovar token TikTok Shop.")


def fetch_paginated_rows(
    *,
    endpoint: str,
    auth: TikTokShopAuth,
    access_token: str,
    shop_cipher: str,
    shop_id: str,
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    if not str(auth.app_key or "").strip() or not str(auth.app_secret or "").strip():
        raise ValueError("Credenciais TikTok Shop incompletas: app_key/app_secret ausentes.")

    rows: list[dict[str, Any]] = []
    method, path, fixed_query = _resolve_endpoint_spec(endpoint)
    page = 1
    next_page_token = ""
    try_without_period = False

    while page <= MAX_PAGES_SAFETY:
        request_body = _build_request_body(
            method=method,
            path=path,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=DEFAULT_PAGE_SIZE,
            next_page_token=next_page_token,
            include_period=not try_without_period,
        )
        request_query = _build_request_query(
            fixed_query=fixed_query,
            access_token=access_token,
            shop_cipher=shop_cipher,
            shop_id=shop_id,
        )
        try:
            response_payload = _request_resource(
                method=method,
                path=path,
                query=request_query,
                body=request_body,
                app_key=auth.app_key,
                app_secret=auth.app_secret,
            )
        except TikTokShopAPIError as error:
            if not try_without_period and _can_retry_without_period(error):
                try_without_period = True
                continue
            raise

        data = _extract_data_block(response_payload)
        page_rows = _extract_rows(data)
        rows.extend(page_rows)

        new_next_page_token = str(
            data.get("next_page_token") or data.get("page_token") or ""
        ).strip()
        if new_next_page_token and new_next_page_token != next_page_token:
            next_page_token = new_next_page_token
            page += 1
            continue

        if _has_next_page(
            data=data,
            current_page=page,
            default_page_size=DEFAULT_PAGE_SIZE,
            received_count=len(page_rows),
        ):
            page += 1
            continue
        break

    return rows


def _request_resource(
    *,
    method: str,
    path: str,
    query: dict[str, object],
    body: dict[str, object],
    app_key: str,
    app_secret: str,
) -> dict[str, Any]:
    params = {**query}
    params["app_key"] = app_key
    params["timestamp"] = int(time.time())

    normalized_body = body if method == "POST" else {}
    params["sign"] = _build_sign(
        path=path,
        params=params,
        body=normalized_body,
        app_secret=app_secret,
    )

    url = _build_resource_url(path=path, params=params)
    request_body = None
    headers = {"Accept": "application/json"}
    if method == "POST":
        headers["Content-Type"] = "application/json"
        request_body = json.dumps(normalized_body, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )

    for attempt, backoff in enumerate((*RETRY_BACKOFF_SECONDS, None), start=1):
        request = Request(url=url, method=method, headers=headers, data=request_body)
        try:
            with urlopen(request, timeout=60) as response:
                raw_content = response.read().decode("utf-8")
                if not raw_content.strip():
                    return {}
                decoded = json.loads(raw_content)
                if not isinstance(decoded, dict):
                    raise TikTokShopAPIError("Resposta invalida da API TikTok Shop.")
                _validate_business_error(decoded)
                return decoded
        except HTTPError as error:
            response_body = error.read().decode("utf-8", errors="ignore") if error.fp else ""
            if error.code in {408, 429, 500, 502, 503, 504} and backoff is not None:
                logger.warning(
                    "TikTok Shop HTTP %s (tentativa=%s). Novo retry em %.1fs.",
                    error.code,
                    attempt,
                    backoff,
                )
                time.sleep(backoff)
                continue
            raise TikTokShopAPIError(
                f"Erro HTTP TikTok Shop (status={error.code}): {response_body[:500]}"
            ) from error
        except (URLError, TimeoutError, socket.timeout) as error:
            if backoff is not None:
                logger.warning(
                    "Erro de rede TikTok Shop (tentativa=%s). Novo retry em %.1fs. Erro=%s",
                    attempt,
                    backoff,
                    error,
                )
                time.sleep(backoff)
                continue
            raise TikTokShopAPIError(f"Erro de conexao TikTok Shop: {error}") from error
        except json.JSONDecodeError as error:
            raise TikTokShopAPIError("Resposta JSON invalida da TikTok Shop API.") from error

    raise TikTokShopAPIError("Falha inesperada em chamada TikTok Shop API.")


def _request_auth_json(endpoint: str, payload: dict[str, object]) -> dict[str, Any]:
    url = _build_auth_url(endpoint)
    request_body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    for attempt, backoff in enumerate((*RETRY_BACKOFF_SECONDS, None), start=1):
        request = Request(url=url, method="POST", headers=headers, data=request_body)
        try:
            with urlopen(request, timeout=60) as response:
                raw_content = response.read().decode("utf-8")
                if not raw_content.strip():
                    return {}
                decoded = json.loads(raw_content)
                if not isinstance(decoded, dict):
                    raise TikTokShopAPIError("Resposta invalida no OAuth TikTok Shop.")
                _validate_business_error(decoded)
                return decoded
        except HTTPError as error:
            response_body = error.read().decode("utf-8", errors="ignore") if error.fp else ""
            if error.code in {408, 429, 500, 502, 503, 504} and backoff is not None:
                logger.warning(
                    "TikTok Shop OAuth HTTP %s (tentativa=%s). Retry em %.1fs.",
                    error.code,
                    attempt,
                    backoff,
                )
                time.sleep(backoff)
                continue
            raise TikTokShopAPIError(
                f"Erro HTTP TikTok Shop OAuth (status={error.code}): {response_body[:500]}"
            ) from error
        except (URLError, TimeoutError, socket.timeout) as error:
            if backoff is not None:
                logger.warning(
                    "Erro de rede TikTok Shop OAuth (tentativa=%s). Retry em %.1fs. Erro=%s",
                    attempt,
                    backoff,
                    error,
                )
                time.sleep(backoff)
                continue
            raise TikTokShopAPIError(f"Erro de conexao TikTok Shop OAuth: {error}") from error
        except json.JSONDecodeError as error:
            raise TikTokShopAPIError("Resposta JSON invalida no OAuth TikTok Shop.") from error

    raise TikTokShopAPIError("Falha inesperada em chamada TikTok Shop OAuth.")


def _resolve_endpoint_spec(endpoint: str) -> tuple[str, str, dict[str, str]]:
    text = str(endpoint or "").strip()
    if not text:
        raise ValueError("Endpoint TikTok Shop nao configurado no recurso.")

    method = "POST"
    path_with_query = text
    if " " in text:
        maybe_method, maybe_path = text.split(" ", maxsplit=1)
        upper_method = maybe_method.strip().upper()
        if upper_method in {"GET", "POST"}:
            method = upper_method
            path_with_query = maybe_path.strip()

    parsed = urlparse(path_with_query)
    if parsed.scheme and parsed.netloc:
        path = parsed.path
        query_pairs = dict(parse_qsl(parsed.query, keep_blank_values=True))
    else:
        parsed_local = urlparse(path_with_query if "?" in path_with_query else f"{path_with_query}?")
        path = parsed_local.path
        query_pairs = dict(parse_qsl(parsed_local.query, keep_blank_values=True))

    normalized_path = str(path or "").strip()
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"
    if method not in {"GET", "POST"}:
        method = "POST"
    if " " not in text:
        lower_path = normalized_path.casefold()
        if "/search" in lower_path or "/query" in lower_path:
            method = "POST"
        else:
            method = "GET"

    return method, normalized_path, query_pairs


def _build_request_query(
    *,
    fixed_query: dict[str, str],
    access_token: str,
    shop_cipher: str,
    shop_id: str,
) -> dict[str, object]:
    query: dict[str, object] = {key: value for key, value in fixed_query.items() if str(key).strip()}

    version = str(query.get("version") or os.getenv("TIKTOK_SHOP_API_VERSION") or "").strip()
    if version:
        query["version"] = version
    if access_token:
        query["access_token"] = access_token
    if shop_cipher:
        query["shop_cipher"] = shop_cipher
    if shop_id:
        query["shop_id"] = shop_id
    return query


def _build_request_body(
    *,
    method: str,
    path: str,
    start_date: str,
    end_date: str,
    page: int,
    page_size: int,
    next_page_token: str,
    include_period: bool,
) -> dict[str, object]:
    if method != "POST":
        return {}

    body: dict[str, object] = {
        "page_size": page_size,
    }
    if next_page_token:
        body["page_token"] = next_page_token
        body["next_page_token"] = next_page_token
    else:
        body["page_no"] = page
        body["page"] = page

    if include_period:
        body.update(_build_period_filters(path=path, start_date=start_date, end_date=end_date))

    return body


def _build_period_filters(path: str, start_date: str, end_date: str) -> dict[str, object]:
    from_env = str(os.getenv("TIKTOK_SHOP_DATE_FROM_KEY") or "").strip()
    to_env = str(os.getenv("TIKTOK_SHOP_DATE_TO_KEY") or "").strip()
    if from_env and to_env:
        return {
            from_env: _date_to_timestamp(start_date, end_of_day=False),
            to_env: _date_to_timestamp(end_date, end_of_day=True),
        }

    lower_path = path.casefold()
    if "order" in lower_path:
        return {
            "create_time_from": _date_to_timestamp(start_date, end_of_day=False),
            "create_time_to": _date_to_timestamp(end_date, end_of_day=True),
        }
    return {}


def _build_sign(
    *,
    path: str,
    params: dict[str, object],
    body: dict[str, object],
    app_secret: str,
) -> str:
    sign_input = str(path or "").strip()
    for key in sorted(params.keys()):
        if key in {"sign", "access_token", "app_secret"}:
            continue
        value = params.get(key)
        if value in (None, ""):
            continue
        sign_input += f"{key}{value}"

    if body:
        sign_input += json.dumps(body, ensure_ascii=False, separators=(",", ":"))

    plain = f"{app_secret}{sign_input}{app_secret}"
    return hmac.new(app_secret.encode("utf-8"), plain.encode("utf-8"), hashlib.sha256).hexdigest()


def _build_resource_url(path: str, params: dict[str, object]) -> str:
    base_url = str(os.getenv("TIKTOK_SHOP_API_BASE_URL") or BASE_URL).strip().rstrip("/")
    query = urlencode(
        {
            key: str(value)
            for key, value in params.items()
            if str(key).strip() and value not in (None, "")
        }
    )
    normalized_path = str(path or "").strip()
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"
    return f"{base_url}{normalized_path}?{query}" if query else f"{base_url}{normalized_path}"


def _build_auth_url(endpoint: str) -> str:
    base_url = str(os.getenv("TIKTOK_SHOP_AUTH_BASE_URL") or AUTH_BASE_URL).strip().rstrip("/")
    normalized_endpoint = str(endpoint or "").strip()
    if not normalized_endpoint:
        raise ValueError("Endpoint OAuth TikTok Shop nao configurado.")
    if not normalized_endpoint.startswith("/"):
        normalized_endpoint = f"/{normalized_endpoint}"
    return f"{base_url}{normalized_endpoint}"


def _extract_token_bundle(payload: dict[str, Any]) -> dict[str, Any]:
    data = _extract_data_block(payload)
    token_bundle = {
        "access_token": str(
            data.get("access_token") or payload.get("access_token") or ""
        ).strip(),
        "refresh_token": str(
            data.get("refresh_token") or payload.get("refresh_token") or ""
        ).strip(),
        "shop_cipher": str(
            data.get("shop_cipher")
            or data.get("cipher")
            or payload.get("shop_cipher")
            or ""
        ).strip(),
        "shop_id": str(data.get("shop_id") or payload.get("shop_id") or "").strip(),
        "open_id": str(data.get("open_id") or payload.get("open_id") or "").strip(),
        "seller_name": str(
            data.get("seller_name")
            or data.get("shop_name")
            or payload.get("seller_name")
            or ""
        ).strip(),
        "raw": data,
    }
    if not token_bundle["access_token"]:
        raise TikTokShopAPIError("Resposta OAuth TikTok Shop sem access_token.")
    return token_bundle


def _extract_data_block(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    return {}


def _extract_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = [
        data.get("list"),
        data.get("items"),
        data.get("orders"),
        data.get("products"),
        data.get("records"),
        data.get("data"),
    ]
    for candidate in candidates:
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
    return []


def _validate_business_error(payload: dict[str, Any]) -> None:
    code = payload.get("code")
    if code in (None, 0, "0", 200, "200", "OK", "ok", "SUCCESS", "success"):
        return

    message = str(payload.get("message") or payload.get("msg") or "Erro desconhecido")
    request_id = str(payload.get("request_id") or payload.get("requestId") or "").strip()
    request_suffix = f" request_id={request_id}" if request_id else ""
    raise TikTokShopAPIError(f"TikTok Shop API error code={code}: {message}.{request_suffix}")


def _has_next_page(
    *,
    data: dict[str, Any],
    current_page: int,
    default_page_size: int,
    received_count: int,
) -> bool:
    for key in ("has_more", "more", "has_next_page"):
        raw_value = data.get(key)
        if isinstance(raw_value, bool):
            return raw_value

    page_info = data.get("page_info")
    if isinstance(page_info, dict):
        current = _to_int(page_info.get("page_no") or page_info.get("page") or current_page)
        total_pages = _to_int(page_info.get("total_page") or page_info.get("total_pages"))
        if total_pages > 0:
            return current < total_pages

        total_rows = _to_int(page_info.get("total_count") or page_info.get("total"))
        page_size = _to_int(page_info.get("page_size") or page_info.get("size")) or default_page_size
        if total_rows > 0 and page_size > 0:
            return current * page_size < total_rows

    return received_count >= default_page_size


def _parse_date(raw_value: str | None, default_value: date) -> date:
    if raw_value is None or str(raw_value).strip() == "":
        return default_value
    return date.fromisoformat(str(raw_value).strip())


def _date_to_timestamp(iso_date: str, *, end_of_day: bool) -> int:
    parsed = date.fromisoformat(str(iso_date).strip())
    base = datetime(parsed.year, parsed.month, parsed.day, 23 if end_of_day else 0, 59 if end_of_day else 0, 59 if end_of_day else 0)
    return int(base.timestamp())


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


def _can_retry_without_period(error: Exception) -> bool:
    text = str(error).upper()
    has_param_hint = any(token in text for token in ("PARAM", "INVALID", "UNKNOWN", "UNSUPPORTED"))
    has_date_hint = any(token in text for token in ("DATE", "TIME", "CREATE_TIME", "UPDATE_TIME"))
    return has_param_hint and has_date_hint
