from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TikTokAdsAuth:
    access_token: str = ""
    app_id: str = ""
    secret: str = ""
    redirect_uri: str = ""


@dataclass(frozen=True)
class TikTokAdsAccount:
    company_name: str
    account_name: str
    advertiser_id: str
    cost_center: str = ""
    business_center_name: str = ""
    access_token: str = ""


class TikTokAdsCredentialsStore:
    def __init__(
        self,
        auth: TikTokAdsAuth,
        accounts: list[TikTokAdsAccount],
        credentials_path: Path | None = None,
    ) -> None:
        self.auth = auth
        self._accounts = accounts
        self.credentials_path = credentials_path

    @classmethod
    def from_file(cls, credentials_path: Path) -> "TikTokAdsCredentialsStore":
        if not credentials_path.exists():
            raise FileNotFoundError(
                f"Arquivo de credenciais TikTok Ads nao encontrado: {credentials_path}"
            )

        data = json.loads(credentials_path.read_text(encoding="utf-8-sig"))
        auth_payload = data.get("auth") or {}
        if not isinstance(auth_payload, dict):
            raise ValueError("Formato invalido para auth nas credenciais TikTok Ads.")

        auth = _auth_from_env(
            TikTokAdsAuth(
                access_token=str(auth_payload.get("access_token") or "").strip(),
                app_id=str(auth_payload.get("app_id") or auth_payload.get("client_key") or "").strip(),
                secret=str(
                    auth_payload.get("secret")
                    or auth_payload.get("app_secret")
                    or auth_payload.get("client_secret")
                    or ""
                ).strip(),
                redirect_uri=str(auth_payload.get("redirect_uri") or "").strip(),
            )
        )

        accounts_payload = data.get("accounts") or []
        if not isinstance(accounts_payload, list):
            raise ValueError("Formato invalido para accounts nas credenciais TikTok Ads.")

        accounts = [
            TikTokAdsAccount(
                company_name=str(item.get("company_name") or "").strip(),
                account_name=str(item.get("account_name") or "").strip(),
                advertiser_id=_normalize_advertiser_id(
                    str(item.get("advertiser_id") or item.get("account_id") or "").strip()
                ),
                cost_center=str(item.get("cost_center") or "").strip(),
                business_center_name=str(item.get("business_center_name") or "").strip(),
                access_token=str(item.get("access_token") or "").strip(),
            )
            for item in accounts_payload
            if isinstance(item, dict)
        ]
        valid_accounts = [
            account
            for account in accounts
            if account.company_name and account.account_name and account.advertiser_id
        ]
        return cls(auth=auth, accounts=valid_accounts, credentials_path=credentials_path)

    def companies(self) -> list[str]:
        return sorted({account.company_name for account in self._accounts if account.company_name})

    def accounts_for_company(self, company_name: str) -> list[TikTokAdsAccount]:
        rows = [account for account in self._accounts if account.company_name == company_name]
        if not rows:
            raise ValueError(f"Empresa '{company_name}' nao encontrada nas contas do TikTok Ads.")
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

    @staticmethod
    def access_token_for_account(account: TikTokAdsAccount, auth: TikTokAdsAuth) -> str:
        return str(account.access_token or auth.access_token).strip()

    def with_auth(self, auth: TikTokAdsAuth) -> "TikTokAdsCredentialsStore":
        return TikTokAdsCredentialsStore(
            auth=auth,
            accounts=list(self._accounts),
            credentials_path=self.credentials_path,
        )

    def with_updated_access_token(self, access_token: str) -> "TikTokAdsCredentialsStore":
        updated_auth = replace(self.auth, access_token=str(access_token or "").strip())
        return self.with_auth(updated_auth)

    def save(self) -> None:
        if self.credentials_path is None:
            raise ValueError("Nao foi possivel salvar: caminho de credenciais TikTok Ads ausente.")

        payload = self.to_payload()
        self.credentials_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "auth": {
                "access_token": self.auth.access_token,
                "app_id": self.auth.app_id,
                "secret": self.auth.secret,
                "redirect_uri": self.auth.redirect_uri,
            },
            "accounts": [
                {
                    "company_name": account.company_name,
                    "account_name": account.account_name,
                    "advertiser_id": account.advertiser_id,
                    "cost_center": account.cost_center,
                    "business_center_name": account.business_center_name,
                    "access_token": account.access_token,
                }
                for account in self._accounts
            ],
        }


def _auth_from_env(base_auth: TikTokAdsAuth) -> TikTokAdsAuth:
    return TikTokAdsAuth(
        access_token=str(os.getenv("TIKTOK_ADS_ACCESS_TOKEN") or base_auth.access_token).strip(),
        app_id=str(os.getenv("TIKTOK_ADS_APP_ID") or base_auth.app_id).strip(),
        secret=str(os.getenv("TIKTOK_ADS_SECRET") or base_auth.secret).strip(),
        redirect_uri=str(os.getenv("TIKTOK_ADS_REDIRECT_URI") or base_auth.redirect_uri).strip(),
    )


def _normalize_advertiser_id(raw_value: str) -> str:
    return "".join(ch for ch in str(raw_value) if ch.isdigit())
