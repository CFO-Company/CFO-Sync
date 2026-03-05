from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MercadoLivreAuth:
    client_id: str
    client_secret: str
    access_token: str
    refresh_token: str
    account_alias: str = ""
    user_id: str = ""
    token_type: str = "bearer"
    expires_in: int = 21600
    access_token_expires_at: str | None = None


class MercadoLivreCredentialsStore:
    def __init__(
        self,
        credentials_path: Path,
        auth: MercadoLivreAuth,
        raw_payload: dict[str, Any],
        company_name: str | None = None,
        has_companies_section: bool = False,
    ) -> None:
        self.credentials_path = credentials_path
        self.auth = auth
        self.company_name = company_name
        self._raw_payload = raw_payload
        self._has_companies_section = has_companies_section

    @classmethod
    def from_file(
        cls,
        credentials_path: Path,
        company_name: str | None = None,
    ) -> "MercadoLivreCredentialsStore":
        if not credentials_path.exists():
            raise FileNotFoundError(
                f"Arquivo de credenciais Mercado Livre nao encontrado: {credentials_path}"
            )

        data = json.loads(credentials_path.read_text(encoding="utf-8-sig"))
        auth_payload, resolved_company_name, has_companies_section = cls._resolve_auth_payload(
            data=data,
            company_name=company_name,
        )

        client_id = str(auth_payload.get("client_id") or auth_payload.get("app_id") or "").strip()
        client_secret = str(auth_payload.get("client_secret") or auth_payload.get("secret_key") or "").strip()
        access_token = str(auth_payload.get("access_token") or "").strip()
        refresh_token = str(auth_payload.get("refresh_token") or "").strip()

        if not client_id or not client_secret:
            raise ValueError(
                "Credenciais Mercado Livre invalidas: client_id/app_id e client_secret/secret_key sao obrigatorios."
            )
        if not access_token or not refresh_token:
            raise ValueError(
                "Credenciais Mercado Livre invalidas: access_token e refresh_token sao obrigatorios."
            )

        expires_in = cls._to_int(auth_payload.get("expires_in"), default=21600)
        auth = MercadoLivreAuth(
            client_id=client_id,
            client_secret=client_secret,
            access_token=access_token,
            refresh_token=refresh_token,
            account_alias=cls._to_optional_text(
                auth_payload.get("account_alias")
                or auth_payload.get("alias")
                or auth_payload.get("filial")
            )
            or "",
            user_id=str(auth_payload.get("user_id") or "").strip(),
            token_type=str(auth_payload.get("token_type") or "bearer").strip() or "bearer",
            expires_in=expires_in,
            access_token_expires_at=cls._normalize_iso(auth_payload.get("access_token_expires_at")),
        )
        return cls(
            credentials_path=credentials_path,
            auth=auth,
            raw_payload=data,
            company_name=resolved_company_name,
            has_companies_section=has_companies_section,
        )

    def save(self) -> None:
        auth_payload = self._auth_to_payload()

        if self._has_companies_section:
            payload = dict(self._raw_payload)
            companies = payload.get("companies")
            if not isinstance(companies, dict):
                raise ValueError(
                    "Formato invalido de credenciais Mercado Livre: secao 'companies' ausente ou invalida."
                )

            if not self.company_name:
                raise ValueError(
                    "Nao foi possivel salvar credenciais Mercado Livre: cliente nao informado para secao 'companies'."
                )

            company_payload = companies.get(self.company_name)
            if isinstance(company_payload, dict):
                updated_company_payload = dict(company_payload)
                updated_company_payload["auth"] = auth_payload
            else:
                updated_company_payload = {"auth": auth_payload}
            companies[self.company_name] = updated_company_payload
            payload["companies"] = companies
        else:
            payload = dict(self._raw_payload)
            payload["auth"] = auth_payload

        self.credentials_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def with_updated_tokens(
        self,
        *,
        access_token: str,
        refresh_token: str,
        expires_in: int,
        user_id: str | None = None,
        token_type: str | None = None,
    ) -> "MercadoLivreCredentialsStore":
        expires_at = datetime.now(UTC) + timedelta(seconds=max(0, int(expires_in)))
        updated_auth = replace(
            self.auth,
            access_token=access_token.strip(),
            refresh_token=refresh_token.strip(),
            expires_in=max(0, int(expires_in)),
            user_id=(user_id if user_id is not None else self.auth.user_id).strip(),
            token_type=(token_type if token_type is not None else self.auth.token_type).strip() or "bearer",
            access_token_expires_at=expires_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        )
        return MercadoLivreCredentialsStore(
            credentials_path=self.credentials_path,
            auth=updated_auth,
            raw_payload=self._raw_payload,
            company_name=self.company_name,
            has_companies_section=self._has_companies_section,
        )

    def access_token_expired(self, tolerance_seconds: int = 120) -> bool:
        expires_at_raw = self.auth.access_token_expires_at
        if not expires_at_raw:
            return True

        expires_at = self._parse_iso_utc(expires_at_raw)
        if expires_at is None:
            return True

        limit = datetime.now(UTC) + timedelta(seconds=max(0, tolerance_seconds))
        return expires_at <= limit

    @staticmethod
    def _to_int(value: Any, default: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        if parsed <= 0:
            return default
        return parsed

    @staticmethod
    def _to_optional_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        return text

    @staticmethod
    def _parse_iso_utc(value: str) -> datetime | None:
        text = str(value).strip()
        if not text:
            return None
        try:
            normalized = text.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @classmethod
    def _normalize_iso(cls, value: Any) -> str | None:
        if value is None:
            return None
        parsed = cls._parse_iso_utc(str(value))
        if parsed is None:
            return None
        return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _auth_to_payload(self) -> dict[str, Any]:
        return {
            "client_id": self.auth.client_id,
            "client_secret": self.auth.client_secret,
            "access_token": self.auth.access_token,
            "refresh_token": self.auth.refresh_token,
            "alias": self.auth.account_alias,
            "user_id": self.auth.user_id,
            "token_type": self.auth.token_type,
            "expires_in": self.auth.expires_in,
            "access_token_expires_at": self.auth.access_token_expires_at,
        }

    @classmethod
    def _resolve_auth_payload(
        cls,
        data: dict[str, Any],
        company_name: str | None,
    ) -> tuple[dict[str, Any], str | None, bool]:
        companies = data.get("companies")
        if isinstance(companies, dict):
            requested = (company_name or "").strip()
            if not requested:
                available = ", ".join(sorted(str(name) for name in companies.keys()))
                raise ValueError(
                    "Arquivo de credenciais Mercado Livre usa secao 'companies'. "
                    f"Informe o cliente para selecionar a conta. Clientes disponiveis: {available}."
                )

            resolved_name = cls._find_company_key(companies, requested)
            if resolved_name is None:
                available = ", ".join(sorted(str(name) for name in companies.keys()))
                raise ValueError(
                    f"Cliente '{company_name}' nao encontrado nas credenciais Mercado Livre. "
                    f"Clientes disponiveis: {available}."
                )

            company_payload = companies.get(resolved_name)
            if not isinstance(company_payload, dict):
                raise ValueError(
                    f"Formato invalido para o cliente '{resolved_name}' nas credenciais Mercado Livre."
                )

            auth_payload = company_payload.get("auth", company_payload)
            if not isinstance(auth_payload, dict):
                raise ValueError(
                    f"Formato invalido de credenciais do cliente '{resolved_name}' no Mercado Livre."
                )
            return auth_payload, resolved_name, True

        auth_payload = data.get("auth", data)
        if not isinstance(auth_payload, dict):
            raise ValueError("Formato invalido de credenciais Mercado Livre.")
        return auth_payload, None, False

    @staticmethod
    def _find_company_key(companies: dict[str, Any], requested: str) -> str | None:
        if requested in companies:
            return requested
        target = requested.strip().casefold()
        for company_key in companies.keys():
            normalized = str(company_key).strip().casefold()
            if normalized == target:
                return str(company_key)
        return None
