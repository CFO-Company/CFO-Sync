from __future__ import annotations

import base64
import json
import socket
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BLING_TOKEN_URL = "https://www.bling.com.br/Api/v3/oauth/token"
BLING_CALLBACK_PATH = "/v1/oauth/bling/callback"
TOKEN_RETRY_BACKOFF_SECONDS = (1.0, 3.0, 8.0)


def exchange_bling_code_for_tokens(
    *,
    client_id: str,
    client_secret: str,
    code: str,
) -> dict[str, Any]:
    cleaned_client_id = _required_text(client_id, field_name="client_id")
    cleaned_client_secret = _required_text(client_secret, field_name="client_secret")
    cleaned_code = _required_text(code, field_name="code")
    body = urlencode(
        {
            "grant_type": "authorization_code",
            "code": cleaned_code,
        }
    ).encode("utf-8")
    basic = base64.b64encode(
        f"{cleaned_client_id}:{cleaned_client_secret}".encode("utf-8")
    ).decode("ascii")

    for backoff in (*TOKEN_RETRY_BACKOFF_SECONDS, None):
        request = Request(
            url=BLING_TOKEN_URL,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "enable-jwt": "1",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            error_body = error.read().decode("utf-8", errors="ignore") if error.fp else ""
            if error.code in {429, 500, 502, 503, 504} and backoff is not None:
                time.sleep(backoff)
                continue
            raise ValueError(f"Falha no OAuth Bling (status={error.code}): {error_body[:300]}") from error
        except (URLError, TimeoutError, socket.timeout) as error:
            if backoff is not None:
                time.sleep(backoff)
                continue
            raise ValueError(f"Falha de conexao no OAuth Bling: {error}") from error
        except json.JSONDecodeError as error:
            raise ValueError("Resposta invalida no OAuth Bling.") from error

        if not isinstance(payload, dict):
            raise ValueError("Resposta invalida no OAuth Bling: esperado objeto JSON.")
        return payload

    raise ValueError("Falha inesperada ao trocar authorization code por tokens no Bling.")


def refresh_bling_access_token(
    *,
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> dict[str, Any]:
    cleaned_client_id = _required_text(client_id, field_name="client_id")
    cleaned_client_secret = _required_text(client_secret, field_name="client_secret")
    cleaned_refresh_token = _required_text(refresh_token, field_name="refresh_token")
    body = urlencode(
        {
            "grant_type": "refresh_token",
            "refresh_token": cleaned_refresh_token,
        }
    ).encode("utf-8")
    basic = base64.b64encode(
        f"{cleaned_client_id}:{cleaned_client_secret}".encode("utf-8")
    ).decode("ascii")

    for backoff in (*TOKEN_RETRY_BACKOFF_SECONDS, None):
        request = Request(
            url=BLING_TOKEN_URL,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "enable-jwt": "1",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            error_body = error.read().decode("utf-8", errors="ignore") if error.fp else ""
            if error.code in {429, 500, 502, 503, 504} and backoff is not None:
                time.sleep(backoff)
                continue
            raise ValueError(f"Falha no refresh OAuth Bling (status={error.code}): {error_body[:300]}") from error
        except (URLError, TimeoutError, socket.timeout) as error:
            if backoff is not None:
                time.sleep(backoff)
                continue
            raise ValueError(f"Falha de conexao no refresh OAuth Bling: {error}") from error
        except json.JSONDecodeError as error:
            raise ValueError("Resposta invalida no refresh OAuth Bling.") from error

        if not isinstance(payload, dict):
            raise ValueError("Resposta invalida no refresh OAuth Bling: esperado objeto JSON.")
        return payload

    raise ValueError("Falha inesperada ao renovar access token no Bling.")


def load_bling_app_credentials(credentials_dir: Path) -> dict[str, str]:
    path = credentials_dir / "bling_oauth_app.json"
    if not path.exists():
        raise FileNotFoundError(
            "Credenciais do app Bling nao encontradas. Crie secrets/bling_oauth_app.json "
            "com client_id, client_secret e redirect_uri."
        )

    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Arquivo bling_oauth_app.json invalido: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("Arquivo bling_oauth_app.json invalido: esperado objeto JSON.")

    client_id = _required_text(payload.get("client_id"), field_name="client_id")
    client_secret = _required_text(payload.get("client_secret"), field_name="client_secret")
    redirect_uri = _required_text(payload.get("redirect_uri"), field_name="redirect_uri")
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    }


def save_bling_token_bundle(
    *,
    credentials_dir: Path,
    token_payload: dict[str, Any],
    state: str,
    redirect_uri: str,
) -> dict[str, Any]:
    access_token = _required_text(token_payload.get("access_token"), field_name="access_token")
    refresh_token = _required_text(token_payload.get("refresh_token"), field_name="refresh_token")
    expires_in = _parse_int(token_payload.get("expires_in"), default=21600)
    expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
    token_type = str(token_payload.get("token_type") or "Bearer").strip() or "Bearer"
    scope = str(token_payload.get("scope") or "").strip()

    path = credentials_dir / "bling_oauth_tokens.json"
    payload = _read_json_object(path)
    tokens = payload.get("tokens")
    if not isinstance(tokens, list):
        tokens = []

    entry = {
        "authorized_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "state": str(state or "").strip(),
        "redirect_uri": redirect_uri,
        "token_type": token_type,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": expires_in,
        "access_token_expires_at": expires_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    if scope:
        entry["scope"] = scope

    tokens.append(entry)
    payload["tokens"] = tokens
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "path": str(path),
        "token_count": len(tokens),
        "token_type": token_type,
        "expires_in": expires_in,
        "access_token_expires_at": entry["access_token_expires_at"],
    }


def build_bling_callback_uri(external_base_url: str) -> str:
    base = _required_text(external_base_url, field_name="external_base_url").rstrip("/")
    return f"{base}{BLING_CALLBACK_PATH}"


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Arquivo {path.name} invalido: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"Arquivo {path.name} invalido: esperado objeto JSON.")
    return payload


def _required_text(value: object, *, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"Campo obrigatorio ausente: {field_name}")
    return text


def _parse_int(value: object, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
