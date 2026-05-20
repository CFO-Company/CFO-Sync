from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


MERCADO_PAGO_DEFAULT_BASE_URL = "https://api.mercadopago.com"


@dataclass(frozen=True)
class MercadoPagoAppAuth:
    client_id: str
    client_secret: str
    public_key: str = ""
    access_token: str = ""
    redirect_uri: str = ""


@dataclass(frozen=True)
class MercadoPagoAccount:
    company_name: str
    account_name: str
    account_id: str
    public_key: str
    access_token: str
    base_url: str
    refresh_token: str = ""
    client_id: str = ""
    client_secret: str = ""
    token_type: str = "bearer"
    expires_in: int = 21600
    access_token_expires_at: str | None = None


class MercadoPagoCredentialsStore:
    def __init__(
        self,
        *,
        credentials_path: Path,
        accounts: list[MercadoPagoAccount],
        base_url: str,
        raw_payload: dict[str, Any],
        auth: MercadoPagoAppAuth | None = None,
    ) -> None:
        self.credentials_path = credentials_path
        self._accounts = accounts
        self.base_url = base_url
        self.auth = auth
        self._raw_payload = raw_payload

    @classmethod
    def from_file(cls, credentials_path: Path) -> "MercadoPagoCredentialsStore":
        if not credentials_path.exists():
            raise FileNotFoundError(
                f"Arquivo de credenciais Mercado Pago nao encontrado: {credentials_path}"
            )

        data = json.loads(credentials_path.read_text(encoding="utf-8-sig"))
        base_url = str(data.get("base_url") or MERCADO_PAGO_DEFAULT_BASE_URL).strip().rstrip("/")
        auth = cls._parse_app_auth(data.get("auth"))
        accounts: list[MercadoPagoAccount] = []

        for company_name, entries in (data.get("companies") or {}).items():
            for item in entries or []:
                accounts.append(
                    MercadoPagoAccount(
                        company_name=str(company_name or "").strip(),
                        account_name=str(item.get("account_name") or item.get("alias") or "").strip(),
                        account_id=str(item.get("account_id") or item.get("user_id") or "").strip(),
                        public_key=str(item.get("public_key") or "").strip(),
                        access_token=str(item.get("access_token") or "").strip(),
                        base_url=str(item.get("base_url") or base_url).strip().rstrip("/"),
                        refresh_token=str(item.get("refresh_token") or "").strip(),
                        client_id=str(item.get("client_id") or (auth.client_id if auth else "")).strip(),
                        client_secret=str(
                            item.get("client_secret") or (auth.client_secret if auth else "")
                        ).strip(),
                        token_type=str(item.get("token_type") or "bearer").strip() or "bearer",
                        expires_in=cls._to_int(item.get("expires_in"), default=21600),
                        access_token_expires_at=cls._normalize_iso(
                            item.get("access_token_expires_at")
                        ),
                    )
                )

        valid_accounts = [account for account in accounts if account.company_name and account.account_name]
        if not valid_accounts and not auth:
            raise ValueError(
                f"Nenhuma credencial Mercado Pago valida encontrada em: {credentials_path}"
            )

        return cls(
            credentials_path=credentials_path,
            accounts=valid_accounts,
            base_url=base_url,
            raw_payload=data,
            auth=auth,
        )

    def companies(self) -> list[str]:
        return sorted({account.company_name for account in self._accounts})

    def accounts_for_company(self, company_name: str) -> list[MercadoPagoAccount]:
        items = [account for account in self._accounts if account.company_name == company_name]
        if not items:
            raise ValueError(f"Empresa '{company_name}' nao encontrada no cadastro do Mercado Pago.")
        return items

    def account_names_for_company(self, company_name: str) -> list[str]:
        seen: set[str] = set()
        names: list[str] = []
        for account in self.accounts_for_company(company_name):
            if account.account_name in seen:
                continue
            seen.add(account.account_name)
            names.append(account.account_name)
        return names

    def access_token_expired(
        self,
        *,
        account: MercadoPagoAccount,
        tolerance_seconds: int = 600,
    ) -> bool:
        expires_at_raw = account.access_token_expires_at
        if not expires_at_raw:
            return bool(account.refresh_token)

        expires_at = self._parse_iso_utc(expires_at_raw)
        if expires_at is None:
            return bool(account.refresh_token)

        limit = datetime.now(UTC) + timedelta(seconds=max(0, tolerance_seconds))
        return expires_at <= limit

    def with_updated_account_tokens(
        self,
        *,
        company_name: str,
        account_name: str,
        access_token: str,
        refresh_token: str,
        expires_in: int,
        account_id: str | None = None,
        public_key: str | None = None,
        token_type: str | None = None,
    ) -> "MercadoPagoCredentialsStore":
        expires_at = datetime.now(UTC) + timedelta(seconds=max(0, int(expires_in)))
        updated_accounts: list[MercadoPagoAccount] = []
        updated_account: MercadoPagoAccount | None = None
        for account in self._accounts:
            if (
                account.company_name.strip().casefold() == company_name.strip().casefold()
                and account.account_name.strip().casefold() == account_name.strip().casefold()
            ):
                updated_account = replace(
                    account,
                    access_token=access_token.strip(),
                    refresh_token=refresh_token.strip() or account.refresh_token,
                    expires_in=max(0, int(expires_in)),
                    account_id=(account_id if account_id is not None else account.account_id).strip(),
                    public_key=(public_key if public_key is not None else account.public_key).strip(),
                    token_type=(token_type if token_type is not None else account.token_type).strip()
                    or "bearer",
                    access_token_expires_at=expires_at.replace(microsecond=0)
                    .isoformat()
                    .replace("+00:00", "Z"),
                )
                updated_accounts.append(updated_account)
                continue
            updated_accounts.append(account)

        if updated_account is None:
            raise ValueError(
                f"Conta '{account_name}' do cliente '{company_name}' nao encontrada no Mercado Pago."
            )

        return MercadoPagoCredentialsStore(
            credentials_path=self.credentials_path,
            accounts=updated_accounts,
            base_url=self.base_url,
            raw_payload=self._raw_payload,
            auth=self.auth,
        )

    def save(self) -> None:
        payload = dict(self._raw_payload)
        payload["base_url"] = self.base_url
        if self.auth is not None:
            payload["auth"] = {
                "client_id": self.auth.client_id,
                "client_secret": self.auth.client_secret,
                "public_key": self.auth.public_key,
                "access_token": self.auth.access_token,
                "redirect_uri": self.auth.redirect_uri,
            }

        companies: dict[str, list[dict[str, Any]]] = {}
        for account in self._accounts:
            companies.setdefault(account.company_name, []).append(
                {
                    "account_name": account.account_name,
                    "account_id": account.account_id,
                    "public_key": account.public_key,
                    "access_token": account.access_token,
                    "refresh_token": account.refresh_token,
                    "client_id": account.client_id,
                    "client_secret": account.client_secret,
                    "token_type": account.token_type,
                    "expires_in": account.expires_in,
                    "access_token_expires_at": account.access_token_expires_at,
                }
            )
        payload["companies"] = companies
        self.credentials_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _parse_app_auth(value: object) -> MercadoPagoAppAuth | None:
        if not isinstance(value, dict):
            return None
        client_id = str(value.get("client_id") or value.get("app_id") or "").strip()
        client_secret = str(value.get("client_secret") or value.get("secret_key") or "").strip()
        if not client_id or not client_secret:
            return None
        return MercadoPagoAppAuth(
            client_id=client_id,
            client_secret=client_secret,
            public_key=str(value.get("public_key") or "").strip(),
            access_token=str(value.get("access_token") or "").strip(),
            redirect_uri=str(value.get("redirect_uri") or "").strip(),
        )

    @staticmethod
    def _to_int(value: object, *, default: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        if parsed <= 0:
            return default
        return parsed

    @staticmethod
    def _parse_iso_utc(value: str) -> datetime | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @classmethod
    def _normalize_iso(cls, value: object) -> str | None:
        if value is None:
            return None
        parsed = cls._parse_iso_utc(str(value))
        if parsed is None:
            return None
        return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")
