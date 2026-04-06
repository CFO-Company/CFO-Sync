from __future__ import annotations

import json
import secrets
import socket
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from cfo_sync.core.config_loader import load_app_config


MERCADO_LIVRE_AUTH_URL = "https://auth.mercadolivre.com.br/authorization"
MERCADO_LIVRE_TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
STATE_TTL_MINUTES = 20
TOKEN_RETRY_BACKOFF_SECONDS = (1.0, 3.0, 8.0)


@dataclass(frozen=True)
class PendingMercadoLivreState:
    state: str
    expires_at: datetime
    redirect_uri: str
    registration_payload: dict[str, object]


@dataclass(frozen=True)
class MercadoLivreAppCredentials:
    client_id: str
    client_secret: str


class GeneratorLinkManager:
    def __init__(self, app_config_path: Path) -> None:
        self.app_config_path = app_config_path
        self._state_lock = RLock()
        self._pending_states: dict[str, PendingMercadoLivreState] = {}

    def create_link(
        self,
        payload: dict[str, object],
        *,
        external_base_url: str,
    ) -> dict[str, object]:
        platform_key = _required_text(payload.get("platform_key"), field_name="platform_key")
        if platform_key != "mercado_livre":
            raise ValueError(
                f"Gerador ainda nao suportado para plataforma '{platform_key}'. "
                "No momento use Mercado Livre."
            )

        registration_mode = _registration_mode(payload.get("registration_mode"))
        requested_client_name = _required_text(payload.get("client_name"), field_name="client_name")
        gid = _parse_gid(payload.get("gid"), field_name="gid")
        raw_credentials = payload.get("credentials")
        credentials_payload = raw_credentials if isinstance(raw_credentials, dict) else {}

        app_config = load_app_config(self.app_config_path)
        platform = next((item for item in app_config.platforms if item.key == platform_key), None)
        if platform is None:
            raise ValueError(f"Plataforma nao registrada: {platform_key}")

        if registration_mode == "new_client":
            client_name = _resolve_new_name(
                candidates=platform.clients,
                requested=requested_client_name,
                conflict_message=(
                    f"Cliente '{requested_client_name}' ja existe na plataforma '{platform_key}'. "
                    "Use o modo de filial/alias para atualizar credenciais."
                ),
            )
        else:
            client_name = _resolve_existing_name(
                candidates=platform.clients,
                requested=requested_client_name,
                not_found_message=(
                    f"Cliente '{requested_client_name}' nao encontrado na plataforma '{platform_key}'. "
                    "Selecione um cliente existente."
                ),
            )

        app_credentials = self._resolve_mercado_livre_app_credentials(
            credentials_dir=app_config.credentials_dir,
        )
        redirect_uri = _build_mercado_livre_callback_uri(external_base_url)
        state = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(minutes=STATE_TTL_MINUTES)

        registration_payload: dict[str, object] = {
            "registration_mode": registration_mode,
            "platform_key": platform_key,
            "client_name": client_name,
            "gid": gid,
            "credentials": {
                "client_id": app_credentials.client_id,
                "client_secret": app_credentials.client_secret,
                "account_alias": _required_text(
                    credentials_payload.get("account_alias"),
                    field_name="credentials.account_alias",
                ),
            },
        }

        pending = PendingMercadoLivreState(
            state=state,
            expires_at=expires_at,
            redirect_uri=redirect_uri,
            registration_payload=registration_payload,
        )
        with self._state_lock:
            self._cleanup_expired_states_locked()
            self._pending_states[state] = pending

        authorization_url = _build_mercado_livre_authorization_url(
            client_id=app_credentials.client_id,
            redirect_uri=redirect_uri,
            state=state,
        )
        return {
            "platform_key": platform_key,
            "registration_mode": registration_mode,
            "client_name": client_name,
            "authorization_url": authorization_url,
            "expires_at": expires_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }

    def consume_mercado_livre_callback(self, *, code: str, state: str) -> dict[str, object]:
        cleaned_code = _required_text(code, field_name="code")
        cleaned_state = _required_text(state, field_name="state")

        with self._state_lock:
            self._cleanup_expired_states_locked()
            pending = self._pending_states.pop(cleaned_state, None)
        if pending is None:
            raise ValueError(
                "State invalido ou expirado. Gere um novo link de autorizacao e tente novamente."
            )
        if pending.expires_at <= datetime.now(UTC):
            raise ValueError("State expirado. Gere um novo link de autorizacao.")

        registration_payload = dict(pending.registration_payload)
        credentials = registration_payload.get("credentials")
        if not isinstance(credentials, dict):
            raise ValueError("Payload interno do gerador invalido: credentials ausente.")

        token_payload = _exchange_mercado_livre_code_for_tokens(
            client_id=_required_text(credentials.get("client_id"), field_name="credentials.client_id"),
            client_secret=_required_text(
                credentials.get("client_secret"),
                field_name="credentials.client_secret",
            ),
            code=cleaned_code,
            redirect_uri=pending.redirect_uri,
        )
        expires_in = _parse_int(token_payload.get("expires_in"), default=21600)
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)

        merged_credentials = dict(credentials)
        merged_credentials.update(
            {
                "access_token": _required_text(
                    token_payload.get("access_token"),
                    field_name="token_payload.access_token",
                ),
                "refresh_token": _required_text(
                    token_payload.get("refresh_token"),
                    field_name="token_payload.refresh_token",
                ),
                "user_id": _optional_text(token_payload.get("user_id")),
                "token_type": _optional_text(token_payload.get("token_type")) or "bearer",
                "expires_in": expires_in,
                "access_token_expires_at": (
                    expires_at.replace(microsecond=0).isoformat().replace("+00:00", "Z")
                ),
            }
        )
        registration_payload["credentials"] = merged_credentials
        return registration_payload

    def _resolve_mercado_livre_app_credentials(self, *, credentials_dir: Path) -> MercadoLivreAppCredentials:
        global_path = credentials_dir / "mercado_livre_oauth_app.json"
        if global_path.exists():
            data = _read_json_file(global_path)
            client_id = _optional_text(data.get("client_id") or data.get("app_id"))
            client_secret = _optional_text(data.get("client_secret") or data.get("secret_key"))
            if client_id and client_secret:
                return MercadoLivreAppCredentials(client_id=client_id, client_secret=client_secret)
            raise ValueError(
                "Arquivo mercado_livre_oauth_app.json invalido: informe client_id/app_id "
                "e client_secret/secret_key."
            )

        credentials_path = credentials_dir / "mercado_livre_credentials.json"
        credentials_data = _read_json_file(credentials_path)

        direct_auth = credentials_data.get("auth")
        if isinstance(direct_auth, dict):
            client_id = _optional_text(direct_auth.get("client_id") or direct_auth.get("app_id"))
            client_secret = _optional_text(
                direct_auth.get("client_secret") or direct_auth.get("secret_key")
            )
            if client_id and client_secret:
                return MercadoLivreAppCredentials(client_id=client_id, client_secret=client_secret)

        companies = credentials_data.get("companies")
        if isinstance(companies, dict):
            for company_payload in companies.values():
                if not isinstance(company_payload, dict):
                    continue
                auth_payload = company_payload.get("auth")
                if not isinstance(auth_payload, dict):
                    auth_payload = company_payload
                client_id = _optional_text(auth_payload.get("client_id") or auth_payload.get("app_id"))
                client_secret = _optional_text(
                    auth_payload.get("client_secret") or auth_payload.get("secret_key")
                )
                if client_id and client_secret:
                    return MercadoLivreAppCredentials(client_id=client_id, client_secret=client_secret)

        raise ValueError(
            "Credenciais globais do app Mercado Livre nao encontradas. "
            "Crie o arquivo secrets/mercado_livre_oauth_app.json com client_id e client_secret."
        )

    def _cleanup_expired_states_locked(self) -> None:
        now = datetime.now(UTC)
        expired = [state for state, item in self._pending_states.items() if item.expires_at <= now]
        for state in expired:
            self._pending_states.pop(state, None)


def _build_mercado_livre_callback_uri(external_base_url: str) -> str:
    base = _required_text(external_base_url, field_name="external_base_url").rstrip("/")
    return f"{base}/v1/oauth/mercado_livre/callback"


def _build_mercado_livre_authorization_url(
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
) -> str:
    query = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
        }
    )
    return f"{MERCADO_LIVRE_AUTH_URL}?{query}"


def _exchange_mercado_livre_code_for_tokens(
    *,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
) -> dict[str, Any]:
    body = urlencode(
        {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        }
    ).encode("utf-8")

    for backoff in (*TOKEN_RETRY_BACKOFF_SECONDS, None):
        request = Request(
            url=MERCADO_LIVRE_TOKEN_URL,
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
            raise ValueError(
                f"Falha no OAuth Mercado Livre (status={error.code}): {error_body[:300]}"
            ) from error
        except (URLError, TimeoutError, socket.timeout) as error:
            if backoff is not None:
                time.sleep(backoff)
                continue
            raise ValueError(f"Falha de conexao no OAuth Mercado Livre: {error}") from error
        except json.JSONDecodeError as error:
            raise ValueError("Resposta invalida no OAuth Mercado Livre.") from error

        if not isinstance(payload, dict):
            raise ValueError("Resposta invalida no OAuth Mercado Livre: esperado objeto JSON.")
        return payload

    raise ValueError("Falha inesperada ao trocar authorization code por tokens no Mercado Livre.")


def _required_text(value: object, *, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"Campo obrigatorio ausente: {field_name}")
    return text


def _optional_text(value: object) -> str:
    return str(value or "").strip()


def _parse_gid(value: object, *, field_name: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if not digits:
        raise ValueError(
            f"Campo '{field_name}' deve conter o GID da aba (sheetId) em numeros."
        )
    return digits


def _registration_mode(value: object) -> str:
    cleaned = str(value or "").strip().casefold()
    if cleaned in {"", "existing_client", "existing", "alias", "filial"}:
        return "existing_client"
    if cleaned in {"new_client", "new", "novo_cliente"}:
        return "new_client"
    raise ValueError(
        "Modo de cadastro invalido. Use 'existing_client' para filial/alias "
        "ou 'new_client' para novo cliente."
    )


def _resolve_existing_name(
    *,
    candidates: list[str],
    requested: str,
    not_found_message: str,
) -> str:
    key = _find_key_case_insensitive(candidates, requested)
    if key is None:
        raise ValueError(not_found_message)
    return key


def _resolve_new_name(
    *,
    candidates: list[str],
    requested: str,
    conflict_message: str,
) -> str:
    resolved = str(requested or "").strip()
    if _find_key_case_insensitive(candidates, resolved) is not None:
        raise ValueError(conflict_message)
    return resolved


def _find_key_case_insensitive(values: Any, target: str) -> str | None:
    normalized_target = str(target or "").strip().casefold()
    if not normalized_target:
        return None
    for value in values:
        text = str(value or "").strip()
        if text.casefold() == normalized_target:
            return text
    return None


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Arquivo nao encontrado: {path}")
    try:
        loaded = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise ValueError(f"JSON invalido em {path}: {error}") from error
    if not isinstance(loaded, dict):
        raise ValueError(f"Arquivo JSON invalido em {path}: raiz deve ser objeto.")
    return loaded


def _parse_int(value: object, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed <= 0:
        return default
    return parsed
