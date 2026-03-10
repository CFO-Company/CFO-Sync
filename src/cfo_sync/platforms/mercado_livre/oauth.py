from __future__ import annotations

import argparse
import json
import socket
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from cfo_sync.core.runtime_paths import default_mercado_livre_credentials_path
from cfo_sync.platforms.mercado_livre.credentials import MercadoLivreAuth, MercadoLivreCredentialsStore


TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
RETRY_BACKOFF_SECONDS = (1.0, 3.0, 8.0)


class MercadoLivreAPIError(RuntimeError):
    pass


def ensure_valid_access_token(
    credentials_path: Path,
    tolerance_seconds: int = 120,
    client: str | None = None,
) -> MercadoLivreAuth:
    store = MercadoLivreCredentialsStore.from_file(credentials_path, company_name=client)
    if not store.access_token_expired(tolerance_seconds=tolerance_seconds):
        return store.auth
    return refresh_access_token(credentials_path, client=client)


def refresh_access_token(credentials_path: Path, client: str | None = None) -> MercadoLivreAuth:
    store = MercadoLivreCredentialsStore.from_file(credentials_path, company_name=client)
    payload = _refresh_token_request(store.auth)

    access_token = str(payload.get("access_token") or "").strip()
    refresh_token = str(payload.get("refresh_token") or "").strip()
    expires_in = _parse_int(payload.get("expires_in"), default=21600)
    if not access_token or not refresh_token:
        raise MercadoLivreAPIError(
            "Resposta invalida do Mercado Livre: access_token/refresh_token ausente."
        )

    updated_store = store.with_updated_tokens(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user_id=_to_optional_text(payload.get("user_id")),
        token_type=_to_optional_text(payload.get("token_type")),
    )
    updated_store.save()
    return updated_store.auth


def _refresh_token_request(auth: MercadoLivreAuth) -> dict[str, Any]:
    body = urlencode(
        {
            "grant_type": "refresh_token",
            "client_id": auth.client_id,
            "client_secret": auth.client_secret,
            "refresh_token": auth.refresh_token,
        }
    ).encode("utf-8")

    for backoff in (*RETRY_BACKOFF_SECONDS, None):
        request = Request(
            url=TOKEN_URL,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            error_body = error.read().decode("utf-8", errors="ignore") if error.fp else ""
            if error.code in {429, 500, 502, 503, 504} and backoff is not None:
                time.sleep(backoff)
                continue
            raise MercadoLivreAPIError(
                f"Erro HTTP no refresh do Mercado Livre (status={error.code}): {error_body[:300]}"
            ) from error
        except (URLError, TimeoutError, socket.timeout) as error:
            if backoff is not None:
                time.sleep(backoff)
                continue
            raise MercadoLivreAPIError(f"Erro de conexao no refresh do Mercado Livre: {error}") from error
        except json.JSONDecodeError as error:
            raise MercadoLivreAPIError("Resposta invalida no refresh do Mercado Livre.") from error

    raise MercadoLivreAPIError("Falha inesperada ao renovar token do Mercado Livre.")


def _parse_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed <= 0:
        return default
    return parsed


def _to_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def _mask(value: str) -> str:
    text = value.strip()
    if len(text) <= 8:
        return "*" * len(text)
    return f"{text[:4]}...{text[-4:]}"


def _main() -> int:
    parser = argparse.ArgumentParser(description="Renova e persiste o token do Mercado Livre.")
    parser.add_argument(
        "--credentials",
        default=str(default_mercado_livre_credentials_path()),
        help="Caminho do JSON de credenciais do Mercado Livre.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Forca refresh mesmo se o access token ainda nao expirou.",
    )
    parser.add_argument(
        "--client",
        default=None,
        help="Nome do cliente quando o arquivo de credenciais usa secao 'companies'.",
    )
    args = parser.parse_args()

    credentials_path = Path(args.credentials)
    auth = (
        refresh_access_token(credentials_path, client=args.client)
        if args.force
        else ensure_valid_access_token(credentials_path, client=args.client)
    )

    print("Token Mercado Livre validado/atualizado com sucesso.")
    print(f"access_token: {_mask(auth.access_token)}")
    print(f"refresh_token: {_mask(auth.refresh_token)}")
    print(f"expires_at: {auth.access_token_expires_at or 'nao informado'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
