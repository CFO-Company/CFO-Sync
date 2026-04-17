from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TikTokShopAuth:
    app_key: str = ""
    app_secret: str = ""
    redirect_uri: str = ""
    access_token: str = ""
    refresh_token: str = ""
    shop_cipher: str = ""
    shop_id: str = ""


@dataclass(frozen=True)
class TikTokShopAccount:
    company_name: str
    account_name: str
    shop_cipher: str = ""
    shop_id: str = ""
    access_token: str = ""


class TikTokShopCredentialsStore:
    def __init__(
        self,
        auth: TikTokShopAuth,
        accounts: list[TikTokShopAccount],
        credentials_path: Path | None = None,
    ) -> None:
        self.auth = auth
        self._accounts = accounts
        self.credentials_path = credentials_path

    @classmethod
    def from_file(cls, credentials_path: Path) -> "TikTokShopCredentialsStore":
        if not credentials_path.exists():
            raise FileNotFoundError(
                f"Arquivo de credenciais TikTok Shop nao encontrado: {credentials_path}"
            )

        data = json.loads(credentials_path.read_text(encoding="utf-8-sig"))
        auth_payload = data.get("auth") or {}
        if not isinstance(auth_payload, dict):
            raise ValueError("Formato invalido para auth nas credenciais TikTok Shop.")

        auth = _auth_from_env(
            TikTokShopAuth(
                app_key=str(auth_payload.get("app_key") or auth_payload.get("client_key") or "").strip(),
                app_secret=str(
                    auth_payload.get("app_secret") or auth_payload.get("client_secret") or ""
                ).strip(),
                redirect_uri=str(auth_payload.get("redirect_uri") or "").strip(),
                access_token=str(auth_payload.get("access_token") or "").strip(),
                refresh_token=str(auth_payload.get("refresh_token") or "").strip(),
                shop_cipher=str(auth_payload.get("shop_cipher") or "").strip(),
                shop_id=str(auth_payload.get("shop_id") or "").strip(),
            )
        )

        accounts_payload = data.get("accounts") or []
        if not isinstance(accounts_payload, list):
            raise ValueError("Formato invalido para accounts nas credenciais TikTok Shop.")

        accounts = [
            TikTokShopAccount(
                company_name=str(item.get("company_name") or "").strip(),
                account_name=str(item.get("account_name") or "").strip(),
                shop_cipher=str(item.get("shop_cipher") or "").strip(),
                shop_id=str(item.get("shop_id") or "").strip(),
                access_token=str(item.get("access_token") or "").strip(),
            )
            for item in accounts_payload
            if isinstance(item, dict)
        ]
        valid_accounts = [
            account for account in accounts if account.company_name and account.account_name
        ]
        return cls(auth=auth, accounts=valid_accounts, credentials_path=credentials_path)

    def companies(self) -> list[str]:
        return sorted({account.company_name for account in self._accounts if account.company_name})

    def accounts_for_company(self, company_name: str) -> list[TikTokShopAccount]:
        rows = [account for account in self._accounts if account.company_name == company_name]
        if not rows:
            raise ValueError(f"Empresa '{company_name}' nao encontrada nas contas do TikTok Shop.")
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
    def access_token_for_account(account: TikTokShopAccount, auth: TikTokShopAuth) -> str:
        return str(account.access_token or auth.access_token).strip()

    @staticmethod
    def shop_cipher_for_account(account: TikTokShopAccount, auth: TikTokShopAuth) -> str:
        return str(account.shop_cipher or auth.shop_cipher).strip()

    @staticmethod
    def shop_id_for_account(account: TikTokShopAccount, auth: TikTokShopAuth) -> str:
        return str(account.shop_id or auth.shop_id).strip()

    def with_auth(self, auth: TikTokShopAuth) -> "TikTokShopCredentialsStore":
        return TikTokShopCredentialsStore(
            auth=auth,
            accounts=list(self._accounts),
            credentials_path=self.credentials_path,
        )

    def with_updated_tokens(
        self,
        *,
        access_token: str,
        refresh_token: str | None = None,
        shop_cipher: str | None = None,
        shop_id: str | None = None,
    ) -> "TikTokShopCredentialsStore":
        updated_auth = replace(
            self.auth,
            access_token=str(access_token or "").strip(),
            refresh_token=str(refresh_token if refresh_token is not None else self.auth.refresh_token).strip(),
            shop_cipher=str(shop_cipher if shop_cipher is not None else self.auth.shop_cipher).strip(),
            shop_id=str(shop_id if shop_id is not None else self.auth.shop_id).strip(),
        )
        return self.with_auth(updated_auth)

    def with_upsert_account(
        self,
        *,
        company_name: str,
        account_name: str,
        shop_cipher: str = "",
        shop_id: str = "",
        access_token: str = "",
    ) -> "TikTokShopCredentialsStore":
        normalized_company = str(company_name or "").strip()
        normalized_account = str(account_name or "").strip()
        if not normalized_company or not normalized_account:
            return self

        updated_accounts: list[TikTokShopAccount] = []
        replaced = False
        for account in self._accounts:
            same_company = account.company_name.casefold() == normalized_company.casefold()
            same_account = account.account_name.casefold() == normalized_account.casefold()
            if same_company and same_account:
                updated_accounts.append(
                    TikTokShopAccount(
                        company_name=account.company_name,
                        account_name=account.account_name,
                        shop_cipher=str(shop_cipher or account.shop_cipher).strip(),
                        shop_id=str(shop_id or account.shop_id).strip(),
                        access_token=str(access_token or account.access_token).strip(),
                    )
                )
                replaced = True
            else:
                updated_accounts.append(account)

        if not replaced:
            updated_accounts.append(
                TikTokShopAccount(
                    company_name=normalized_company,
                    account_name=normalized_account,
                    shop_cipher=str(shop_cipher or "").strip(),
                    shop_id=str(shop_id or "").strip(),
                    access_token=str(access_token or "").strip(),
                )
            )

        return TikTokShopCredentialsStore(
            auth=self.auth,
            accounts=updated_accounts,
            credentials_path=self.credentials_path,
        )

    def save(self) -> None:
        if self.credentials_path is None:
            raise ValueError("Nao foi possivel salvar: caminho de credenciais TikTok Shop ausente.")

        payload = self.to_payload()
        self.credentials_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "auth": {
                "app_key": self.auth.app_key,
                "app_secret": self.auth.app_secret,
                "redirect_uri": self.auth.redirect_uri,
                "access_token": self.auth.access_token,
                "refresh_token": self.auth.refresh_token,
                "shop_cipher": self.auth.shop_cipher,
                "shop_id": self.auth.shop_id,
            },
            "accounts": [
                {
                    "company_name": account.company_name,
                    "account_name": account.account_name,
                    "shop_cipher": account.shop_cipher,
                    "shop_id": account.shop_id,
                    "access_token": account.access_token,
                }
                for account in self._accounts
            ],
        }


def _auth_from_env(base_auth: TikTokShopAuth) -> TikTokShopAuth:
    return TikTokShopAuth(
        app_key=str(os.getenv("TIKTOK_SHOP_APP_KEY") or base_auth.app_key).strip(),
        app_secret=str(os.getenv("TIKTOK_SHOP_APP_SECRET") or base_auth.app_secret).strip(),
        redirect_uri=str(os.getenv("TIKTOK_SHOP_REDIRECT_URI") or base_auth.redirect_uri).strip(),
        access_token=str(os.getenv("TIKTOK_SHOP_ACCESS_TOKEN") or base_auth.access_token).strip(),
        refresh_token=str(os.getenv("TIKTOK_SHOP_REFRESH_TOKEN") or base_auth.refresh_token).strip(),
        shop_cipher=str(os.getenv("TIKTOK_SHOP_SHOP_CIPHER") or base_auth.shop_cipher).strip(),
        shop_id=str(os.getenv("TIKTOK_SHOP_SHOP_ID") or base_auth.shop_id).strip(),
    )
