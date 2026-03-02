from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MetaAdsAuth:
    access_token: str
    app_id: str
    app_secret: str


@dataclass(frozen=True)
class MetaAdsAccount:
    company_name: str
    business_manager_name: str
    ad_account_name: str
    cost_center: str
    account_id: str


class MetaAdsCredentialsStore:
    def __init__(self, auth: MetaAdsAuth, accounts: list[MetaAdsAccount]) -> None:
        self.auth = auth
        self._accounts = accounts

    @classmethod
    def from_file(cls, credentials_path: Path) -> "MetaAdsCredentialsStore":
        if not credentials_path.exists():
            raise FileNotFoundError(f"Arquivo de credenciais Meta Ads nao encontrado: {credentials_path}")

        data = json.loads(credentials_path.read_text(encoding="utf-8-sig"))
        auth = MetaAdsAuth(
            access_token=data["auth"]["access_token"],
            app_id=str(data["auth"]["app_id"]),
            app_secret=data["auth"]["app_secret"],
        )

        accounts = [
            MetaAdsAccount(
                company_name=item["company_name"],
                business_manager_name=item["business_manager_name"],
                ad_account_name=item["ad_account_name"],
                cost_center=item["cost_center"],
                account_id=str(item["account_id"]),
            )
            for item in data["accounts"]
        ]
        return cls(auth=auth, accounts=accounts)

    def companies(self) -> list[str]:
        return sorted({account.company_name for account in self._accounts})

    def accounts_for_company(self, company_name: str) -> list[MetaAdsAccount]:
        rows = [account for account in self._accounts if account.company_name == company_name]
        if not rows:
            raise ValueError(f"Empresa '{company_name}' nao encontrada nas contas do Meta Ads.")
        return rows

    def ad_account_names_for_company(self, company_name: str) -> list[str]:
        accounts = self.accounts_for_company(company_name)
        seen: set[str] = set()
        names: list[str] = []
        for account in accounts:
            name = account.ad_account_name
            if name not in seen:
                seen.add(name)
                names.append(name)
        return names
