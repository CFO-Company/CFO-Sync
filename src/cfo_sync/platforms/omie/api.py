from __future__ import annotations

import json
import re
import socket
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from cfo_sync.platforms.omie.credentials import OmieCredential


BASE_URL = "https://app.omie.com.br/api/v1/"
MAX_ATTEMPTS = 5
BACKOFF_SECONDS = (1.0, 2.0, 4.0, 8.0, 16.0)
RATE_LIMIT_STATUS_CODES = {403, 425, 429, 503}
REQUEST_SPACING_SECONDS = 0.8

_LAST_REQUEST_AT_BY_METHOD: dict[str, float] = {}


class OmieAPIError(RuntimeError):
    pass


def call_omie_api(
    credential: OmieCredential,
    call: str,
    endpoint: str,
    params: dict[str, Any],
) -> dict[str, Any] | None:
    request_key = f"{credential.app_key}::{call}"
    payload = {
        "call": call,
        "app_key": credential.app_key,
        "app_secret": credential.app_secret,
        "param": [params],
    }
    body = json.dumps(payload).encode("utf-8")
    url = f"{BASE_URL}{endpoint}"

    for attempt in range(MAX_ATTEMPTS):
        _wait_for_request_spacing(request_key)
        request = Request(
            url=url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        try:
            with urlopen(request, timeout=60) as response:
                response_text = response.read().decode("utf-8")
                _LAST_REQUEST_AT_BY_METHOD[request_key] = time.monotonic()
                return json.loads(response_text)
        except HTTPError as error:
            response_text = error.read().decode("utf-8", errors="ignore") if error.fp else ""
            _LAST_REQUEST_AT_BY_METHOD[request_key] = time.monotonic()
            if error.code == 500 and "5113" in response_text:
                return None
            if error.code == 500 and _is_temporary_busy_error(response_text) and attempt < MAX_ATTEMPTS - 1:
                time.sleep(_temporary_busy_retry_delay(response_text, attempt))
                continue
            if error.code in RATE_LIMIT_STATUS_CODES and attempt < MAX_ATTEMPTS - 1:
                time.sleep(BACKOFF_SECONDS[attempt])
                continue
            raise OmieAPIError(_build_error_message(call, endpoint, error.code, response_text)) from error
        except (URLError, TimeoutError, socket.timeout) as error:
            _LAST_REQUEST_AT_BY_METHOD[request_key] = time.monotonic()
            if attempt < MAX_ATTEMPTS - 1:
                time.sleep(BACKOFF_SECONDS[attempt])
                continue
            raise OmieAPIError(f"Erro de conexao na Omie em {call}/{endpoint}: {error}") from error
        except json.JSONDecodeError as error:
            raise OmieAPIError(f"Resposta invalida da Omie em {call}/{endpoint}.") from error

    raise OmieAPIError(f"Falha inesperada na Omie em {call}/{endpoint}.")


def _build_error_message(call: str, endpoint: str, status_code: int, response_text: str) -> str:
    detail = response_text.strip()
    if not detail:
        return f"Erro HTTP {status_code} na Omie em {call}/{endpoint}."

    try:
        payload = json.loads(detail)
    except json.JSONDecodeError:
        payload = None

    if isinstance(payload, dict):
        fault_code = str(payload.get("faultcode", "")).strip()
        fault_message = str(payload.get("faultstring", "")).strip()
        if fault_code or fault_message:
            return f"Erro HTTP {status_code} na Omie em {call}/{endpoint}: [{fault_code}] {fault_message}".strip()

    return f"Erro HTTP {status_code} na Omie em {call}/{endpoint}: {detail[:300]}"


def _is_temporary_busy_error(response_text: str) -> bool:
    normalized = str(response_text or "")
    return (
        "SOAP-ENV:Client-1880" in normalized
        or "Ja existe uma requisicao desse metodo sendo executada" in normalized
        or "Já existe uma requisição desse método sendo executada" in normalized
        or "REDUNDANT" in normalized
        or "Consumo redundante detectado" in normalized
    )


def _temporary_busy_retry_delay(response_text: str, attempt: int) -> float:
    wait_seconds = _extract_retry_after_seconds(response_text)
    if wait_seconds is not None:
        return wait_seconds + 2.0
    return BACKOFF_SECONDS[attempt]


def _extract_retry_after_seconds(response_text: str) -> float | None:
    match = re.search(r"Aguarde\s+(\d+(?:[,.]\d+)?)\s+segundos?", str(response_text or ""), re.IGNORECASE)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None


def _wait_for_request_spacing(request_key: str) -> None:
    last_request_at = _LAST_REQUEST_AT_BY_METHOD.get(request_key)
    if last_request_at is None:
        return

    elapsed = time.monotonic() - last_request_at
    remaining = REQUEST_SPACING_SECONDS - elapsed
    if remaining > 0:
        time.sleep(remaining)
