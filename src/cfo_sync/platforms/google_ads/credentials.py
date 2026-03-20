from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GoogleAdsAuth:
    developer_token: str = ""
    client_id: str = ""
    client_secret: str = ""
    refresh_token: str = ""
    login_customer_id: str = ""


@dataclass(frozen=True)
class GoogleAdsAccount:
    company_name: str
    account_name: str
    customer_id: str
    cost_center: str = ""
    manager_account_name: str = ""


class GoogleAdsCredentialsStore:
    def __init__(self, auth: GoogleAdsAuth, accounts: list[GoogleAdsAccount]) -> None:
        self.auth = auth
        self._accounts = accounts

    @classmethod
    def from_file(cls, credentials_path: Path) -> "GoogleAdsCredentialsStore":
        if not credentials_path.exists():
            raise FileNotFoundError(
                f"Arquivo de credenciais Google ADS nao encontrado: {credentials_path}"
            )

        data = json.loads(credentials_path.read_text(encoding="utf-8-sig"))
        auth_payload = data.get("auth") or {}
        if not isinstance(auth_payload, dict):
            raise ValueError("Formato invalido para auth nas credenciais Google ADS.")

        auth = GoogleAdsAuth(
            developer_token=str(auth_payload.get("developer_token") or "").strip(),
            client_id=str(auth_payload.get("client_id") or "").strip(),
            client_secret=str(auth_payload.get("client_secret") or "").strip(),
            refresh_token=str(auth_payload.get("refresh_token") or "").strip(),
            login_customer_id=_normalize_customer_id(
                str(auth_payload.get("login_customer_id") or "").strip()
            ),
        )
        auth = _auth_from_env(auth)

        accounts_payload = data.get("accounts") or []
        if not isinstance(accounts_payload, list):
            raise ValueError("Formato invalido para accounts nas credenciais Google ADS.")

        accounts = [
            GoogleAdsAccount(
                company_name=str(item["company_name"]).strip(),
                account_name=str(item["account_name"]).strip(),
                customer_id=_normalize_customer_id(str(item["customer_id"]).strip()),
                cost_center=str(item.get("cost_center") or "").strip(),
                manager_account_name=str(item.get("manager_account_name") or "").strip(),
            )
            for item in accounts_payload
            if isinstance(item, dict)
        ]
        return cls(auth=auth, accounts=accounts)

    def companies(self) -> list[str]:
        return sorted({account.company_name for account in self._accounts if account.company_name})

    def accounts_for_company(self, company_name: str) -> list[GoogleAdsAccount]:
        rows = [account for account in self._accounts if account.company_name == company_name]
        if not rows:
            raise ValueError(f"Empresa '{company_name}' nao encontrada nas contas do Google ADS.")
        return rows

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


def _auth_from_env(base_auth: GoogleAdsAuth) -> GoogleAdsAuth:
    return GoogleAdsAuth(
        developer_token=str(
            os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN") or base_auth.developer_token
        ).strip(),
        client_id=str(os.getenv("GOOGLE_ADS_CLIENT_ID") or base_auth.client_id).strip(),
        client_secret=str(
            os.getenv("GOOGLE_ADS_CLIENT_SECRET") or base_auth.client_secret
        ).strip(),
        refresh_token=str(
            os.getenv("GOOGLE_ADS_REFRESH_TOKEN") or base_auth.refresh_token
        ).strip(),
        login_customer_id=_normalize_customer_id(
            str(
                os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID")
                or base_auth.login_customer_id
            ).strip()
        ),
    )


def _normalize_customer_id(raw_value: str) -> str:
    return "".join(ch for ch in str(raw_value) if ch.isdigit())
