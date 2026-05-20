from __future__ import annotations

import json
import socket
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from cfo_sync.platforms.mercado_pago.credentials import (
    MercadoPagoAccount,
    MercadoPagoAppAuth,
    MercadoPagoCredentialsStore,
)


MERCADO_PAGO_AUTH_URL = "https://auth.mercadopago.com/authorization"
MERCADO_PAGO_TOKEN_URL = "https://api.mercadopago.com/oauth/token"
MERCADO_PAGO_CALLBACK_PATH = "/v1/oauth/mercado_pago/callback"
DEFAULT_REFRESH_TOLERANCE_SECONDS = 10 * 60
TOKEN_RETRY_BACKOFF_SECONDS = (1.0, 3.0, 8.0)


class MercadoPagoOAuthError(RuntimeError):
    pass


def load_mercado_pago_app_credentials(credentials_dir: Path) -> MercadoPagoAppAuth:
    app_path = credentials_dir / "mercado_pago_oauth_app.json"
    if app_path.exists():
        payload = _read_json_object(app_path)
        auth = _parse_app_auth(payload)
        if auth is not None:
            return auth
        raise ValueError(
            "Arquivo mercado_pago_oauth_app.json invalido: informe client_id e client_secret."
        )

    credentials_path = credentials_dir / "mercado_pago_credentials.json"
    store = MercadoPagoCredentialsStore.from_file(credentials_path)
    if store.auth is None:
        raise ValueError(
            "Credenciais globais do app Mercado Pago nao encontradas. "
            "Crie secrets/mercado_pago_oauth_app.json com client_id, client_secret e redirect_uri."
        )
    return store.auth


def ensure_valid_access_token(
    credentials_path: Path,
    *,
    client: str,
    account_alias: str | None = None,
    tolerance_seconds: int = DEFAULT_REFRESH_TOLERANCE_SECONDS,
) -> MercadoPagoAccount:
    store = MercadoPagoCredentialsStore.from_file(credentials_path)
    account = _select_account(store=store, client=client, account_alias=account_alias)
    if account.access_token and not store.access_token_expired(
        account=account,
        tolerance_seconds=tolerance_seconds,
    ):
        return account
    if not account.refresh_token:
        return account
    return refresh_access_token(
        credentials_path,
        client=client,
        account_alias=account.account_name,
    )


def refresh_access_token(
    credentials_path: Path,
    *,
    client: str,
    account_alias: str,
) -> MercadoPagoAccount:
    store = MercadoPagoCredentialsStore.from_file(credentials_path)
    account = _select_account(store=store, client=client, account_alias=account_alias)
    client_id = account.client_id or (store.auth.client_id if store.auth else "")
    client_secret = account.client_secret or (store.auth.client_secret if store.auth else "")
    if not client_id or not client_secret or not account.refresh_token:
        raise MercadoPagoOAuthError(
            "Credenciais Mercado Pago incompletas para refresh: client_id, client_secret e refresh_token."
        )

    token_payload = refresh_mercado_pago_access_token(
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=account.refresh_token,
    )
    updated_store = store.with_updated_account_tokens(
        company_name=account.company_name,
        account_name=account.account_name,
        access_token=_required_text(token_payload.get("access_token"), field_name="access_token"),
        refresh_token=_optional_text(token_payload.get("refresh_token")) or account.refresh_token,
        expires_in=_parse_int(token_payload.get("expires_in"), default=21600),
        account_id=_optional_text(token_payload.get("user_id")) or account.account_id,
        public_key=account.public_key,
        token_type=_optional_text(token_payload.get("token_type")) or account.token_type,
    )
    updated_store.save()
    return _select_account(
        store=updated_store,
        client=account.company_name,
        account_alias=account.account_name,
    )


def exchange_mercado_pago_code_for_tokens(
    *,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    code_verifier: str | None = None,
) -> dict[str, Any]:
    params = {
        "grant_type": "authorization_code",
        "client_id": _required_text(client_id, field_name="client_id"),
        "client_secret": _required_text(client_secret, field_name="client_secret"),
        "code": _required_text(code, field_name="code"),
        "redirect_uri": _required_text(redirect_uri, field_name="redirect_uri"),
    }
    verifier = _optional_text(code_verifier)
    if verifier:
        params["code_verifier"] = verifier
    return _token_request(params)


def refresh_mercado_pago_access_token(
    *,
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> dict[str, Any]:
    return _token_request(
        {
            "grant_type": "refresh_token",
            "client_id": _required_text(client_id, field_name="client_id"),
            "client_secret": _required_text(client_secret, field_name="client_secret"),
            "refresh_token": _required_text(refresh_token, field_name="refresh_token"),
        }
    )


def _token_request(params: dict[str, str]) -> dict[str, Any]:
    body = urlencode(params).encode("utf-8")
    for backoff in (*TOKEN_RETRY_BACKOFF_SECONDS, None):
        request = Request(
            url=MERCADO_PAGO_TOKEN_URL,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
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
            raise MercadoPagoOAuthError(
                f"Falha no OAuth Mercado Pago (status={error.code}): {error_body[:300]}"
            ) from error
        except (URLError, TimeoutError, socket.timeout) as error:
            if backoff is not None:
                time.sleep(backoff)
                continue
            raise MercadoPagoOAuthError(f"Falha de conexao no OAuth Mercado Pago: {error}") from error
        except json.JSONDecodeError as error:
            raise MercadoPagoOAuthError("Resposta invalida no OAuth Mercado Pago.") from error

        if not isinstance(payload, dict):
            raise MercadoPagoOAuthError("Resposta invalida no OAuth Mercado Pago: esperado objeto JSON.")
        return payload

    raise MercadoPagoOAuthError("Falha inesperada em chamada OAuth Mercado Pago.")


def _select_account(
    *,
    store: MercadoPagoCredentialsStore,
    client: str,
    account_alias: str | None,
) -> MercadoPagoAccount:
    accounts = store.accounts_for_company(client)
    requested = str(account_alias or "").strip().casefold()
    if requested:
        for account in accounts:
            if account.account_name.strip().casefold() == requested:
                return account
        raise ValueError(f"Conta Mercado Pago '{account_alias}' nao encontrada para '{client}'.")
    return accounts[0]


def _parse_app_auth(payload: dict[str, Any]) -> MercadoPagoAppAuth | None:
    client_id = _optional_text(payload.get("client_id") or payload.get("app_id"))
    client_secret = _optional_text(payload.get("client_secret") or payload.get("secret_key"))
    if not client_id or not client_secret:
        return None
    return MercadoPagoAppAuth(
        client_id=client_id,
        client_secret=client_secret,
        public_key=_optional_text(payload.get("public_key")),
        access_token=_optional_text(payload.get("access_token")),
        redirect_uri=_optional_text(payload.get("redirect_uri")),
    )


def _read_json_object(path: Path) -> dict[str, Any]:
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


def _optional_text(value: object) -> str:
    return str(value or "").strip()


def _parse_int(value: object, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed <= 0:
        return default
    return parsed
