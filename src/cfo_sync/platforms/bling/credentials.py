from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BlingAuth:
    client_id: str = ""
    client_secret: str = ""
    redirect_uri: str = ""


@dataclass(frozen=True)
class BlingAccount:
    company_name: str
    account_name: str
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 21600
    access_token_expires_at: str | None = None


class BlingCredentialsStore:
    def __init__(
        self,
        *,
        auth: BlingAuth,
        accounts: list[BlingAccount],
        credentials_path: Path,
        raw_payload: dict[str, Any],
    ) -> None:
        self.auth = auth
        self._accounts = accounts
        self.credentials_path = credentials_path
        self._raw_payload = raw_payload

    @classmethod
    def from_file(cls, credentials_path: Path) -> "BlingCredentialsStore":
        raw_payload = _read_json_object(credentials_path)
        auth = _auth_from_payload(raw_payload.get("auth"))

        app_path = credentials_path.with_name("bling_oauth_app.json")
        if app_path.exists():
            app_payload = _read_json_object(app_path)
            auth = BlingAuth(
                client_id=str(app_payload.get("client_id") or auth.client_id).strip(),
                client_secret=str(app_payload.get("client_secret") or auth.client_secret).strip(),
                redirect_uri=str(app_payload.get("redirect_uri") or auth.redirect_uri).strip(),
            )

        auth = _auth_from_env(auth)
        accounts = _accounts_from_payload(raw_payload)

        if not accounts:
            token_payload = _read_json_object(credentials_path.with_name("bling_oauth_tokens.json"))
            accounts = _accounts_from_payload(token_payload)

        valid_accounts = [
            account
            for account in accounts
            if account.company_name and account.account_name and account.access_token
        ]
        if not valid_accounts:
            raise ValueError("Nenhuma conta Bling autorizada encontrada nas credenciais.")

        return cls(
            auth=auth,
            accounts=valid_accounts,
            credentials_path=credentials_path,
            raw_payload=raw_payload,
        )

    def companies(self) -> list[str]:
        return sorted({account.company_name for account in self._accounts if account.company_name})

    def accounts_for_company(self, company_name: str) -> list[BlingAccount]:
        normalized = str(company_name or "").strip().casefold()
        rows = [
            account
            for account in self._accounts
            if account.company_name.casefold() == normalized
        ]
        if rows:
            return rows
        if len(self._accounts) == 1:
            return list(self._accounts)
        raise ValueError(f"Empresa '{company_name}' nao encontrada nas contas do Bling.")

    def account_names_for_company(self, company_name: str) -> list[str]:
        accounts = self.accounts_for_company(company_name)
        seen: set[str] = set()
        names: list[str] = []
        for account in accounts:
            name = account.account_name
            if not name or name in seen:
                continue
            seen.add(name)
            names.append(name)
        return names

    def access_token_expired(self, account: BlingAccount, tolerance_seconds: int = 120) -> bool:
        expires_at = _parse_iso_utc(account.access_token_expires_at)
        if expires_at is None:
            return True
        return expires_at <= datetime.now(UTC) + timedelta(seconds=max(0, tolerance_seconds))

    def with_updated_account_tokens(
        self,
        account: BlingAccount,
        *,
        access_token: str,
        refresh_token: str,
        token_type: str = "Bearer",
        expires_in: int = 21600,
    ) -> "BlingCredentialsStore":
        expires_at = datetime.now(UTC) + timedelta(seconds=max(0, int(expires_in)))
        updated = replace(
            account,
            access_token=str(access_token or "").strip(),
            refresh_token=str(refresh_token or "").strip(),
            token_type=str(token_type or "Bearer").strip() or "Bearer",
            expires_in=max(0, int(expires_in)),
            access_token_expires_at=expires_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        )
        accounts = [
            updated
            if (
                item.company_name.casefold() == account.company_name.casefold()
                and item.account_name.casefold() == account.account_name.casefold()
            )
            else item
            for item in self._accounts
        ]
        return BlingCredentialsStore(
            auth=self.auth,
            accounts=accounts,
            credentials_path=self.credentials_path,
            raw_payload=self._raw_payload,
        )

    def save(self) -> None:
        payload = dict(self._raw_payload)
        payload["auth"] = {
            "client_id": self.auth.client_id,
            "client_secret": self.auth.client_secret,
            "redirect_uri": self.auth.redirect_uri,
        }
        payload["accounts"] = [_account_to_payload(account) for account in self._accounts]
        self.credentials_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def build_credentials_payload_from_oauth(
    *,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    token_payload: dict[str, Any],
    company_name: str,
    account_name: str,
) -> dict[str, Any]:
    expires_in = _parse_int(token_payload.get("expires_in"), default=21600)
    expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
    return {
        "auth": {
            "client_id": str(client_id or "").strip(),
            "client_secret": str(client_secret or "").strip(),
            "redirect_uri": str(redirect_uri or "").strip(),
        },
        "accounts": [
            {
                "company_name": str(company_name or "").strip() or "Bling",
                "account_name": str(account_name or "").strip() or str(company_name or "").strip() or "Bling",
                "access_token": str(token_payload.get("access_token") or "").strip(),
                "refresh_token": str(token_payload.get("refresh_token") or "").strip(),
                "token_type": str(token_payload.get("token_type") or "Bearer").strip() or "Bearer",
                "expires_in": expires_in,
                "access_token_expires_at": (
                    expires_at.replace(microsecond=0).isoformat().replace("+00:00", "Z")
                ),
            }
        ],
    }


def merge_credentials_payload_from_oauth(
    existing_payload: dict[str, Any],
    *,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    token_payload: dict[str, Any],
    company_name: str,
    account_name: str,
) -> dict[str, Any]:
    merged = dict(existing_payload)
    new_payload = build_credentials_payload_from_oauth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        token_payload=token_payload,
        company_name=company_name,
        account_name=account_name,
    )
    merged["auth"] = new_payload["auth"]

    accounts = merged.get("accounts")
    if not isinstance(accounts, list):
        accounts = []
    new_account = new_payload["accounts"][0]
    target_company = str(new_account.get("company_name") or "").strip().casefold()
    target_account = str(new_account.get("account_name") or "").strip().casefold()

    updated_accounts: list[object] = []
    replaced = False
    for account in accounts:
        if not isinstance(account, dict):
            updated_accounts.append(account)
            continue
        current_company = str(account.get("company_name") or "").strip().casefold()
        current_account = str(account.get("account_name") or "").strip().casefold()
        if current_company == target_company and current_account == target_account:
            updated_accounts.append(new_account)
            replaced = True
        else:
            updated_accounts.append(account)
    if not replaced:
        updated_accounts.append(new_account)
    merged["accounts"] = updated_accounts
    return merged


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


def _auth_from_payload(value: object) -> BlingAuth:
    payload = value if isinstance(value, dict) else {}
    return BlingAuth(
        client_id=str(payload.get("client_id") or "").strip(),
        client_secret=str(payload.get("client_secret") or "").strip(),
        redirect_uri=str(payload.get("redirect_uri") or "").strip(),
    )


def _auth_from_env(base_auth: BlingAuth) -> BlingAuth:
    return BlingAuth(
        client_id=str(os.getenv("BLING_CLIENT_ID") or base_auth.client_id).strip(),
        client_secret=str(os.getenv("BLING_CLIENT_SECRET") or base_auth.client_secret).strip(),
        redirect_uri=str(os.getenv("BLING_REDIRECT_URI") or base_auth.redirect_uri).strip(),
    )


def _accounts_from_payload(payload: dict[str, Any]) -> list[BlingAccount]:
    accounts_payload = payload.get("accounts")
    if accounts_payload is None:
        accounts_payload = payload.get("tokens")
    if isinstance(accounts_payload, dict):
        accounts_payload = list(accounts_payload.values())
    if not isinstance(accounts_payload, list):
        return []

    accounts: list[BlingAccount] = []
    for item in accounts_payload:
        if not isinstance(item, dict):
            continue
        company_name = str(
            item.get("company_name")
            or item.get("client_name")
            or item.get("company")
            or item.get("account_name")
            or "Bling"
        ).strip()
        account_name = str(item.get("account_name") or item.get("alias") or company_name).strip()
        accounts.append(
            BlingAccount(
                company_name=company_name,
                account_name=account_name,
                access_token=str(item.get("access_token") or "").strip(),
                refresh_token=str(item.get("refresh_token") or "").strip(),
                token_type=str(item.get("token_type") or "Bearer").strip() or "Bearer",
                expires_in=_parse_int(item.get("expires_in"), default=21600),
                access_token_expires_at=_normalize_iso(item.get("access_token_expires_at")),
            )
        )
    return accounts


def _account_to_payload(account: BlingAccount) -> dict[str, object]:
    return {
        "company_name": account.company_name,
        "account_name": account.account_name,
        "access_token": account.access_token,
        "refresh_token": account.refresh_token,
        "token_type": account.token_type,
        "expires_in": account.expires_in,
        "access_token_expires_at": account.access_token_expires_at,
    }


def _normalize_iso(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _parse_iso_utc(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_int(value: object, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
