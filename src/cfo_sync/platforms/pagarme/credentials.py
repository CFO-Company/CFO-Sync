from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from cfo_sync.core.runtime_paths import default_pagarme_credentials_path


PAGARME_DEFAULT_BASE_URL = "https://api.pagar.me/core/v5"
PAGARME_CREDENTIALS_PATH = default_pagarme_credentials_path()


@dataclass(frozen=True)
class PagarmeAccount:
    company_name: str
    account_name: str
    account_id: str
    public_key: str
    secret_key: str
    base_url: str


class PagarmeCredentialsStore:
    def __init__(self, accounts: list[PagarmeAccount], base_url: str) -> None:
        self._accounts = accounts
        self.base_url = base_url

    @classmethod
    def from_file(cls, credentials_path: Path) -> "PagarmeCredentialsStore":
        if not credentials_path.exists():
            raise FileNotFoundError(f"Arquivo de credenciais Pagar.me nao encontrado: {credentials_path}")

        data = json.loads(credentials_path.read_text(encoding="utf-8-sig"))
        base_url = str(data.get("base_url") or PAGARME_DEFAULT_BASE_URL).strip().rstrip("/")
        accounts: list[PagarmeAccount] = []

        for company_name, entries in (data.get("companies") or {}).items():
            for item in entries or []:
                accounts.append(
                    PagarmeAccount(
                        company_name=str(company_name or "").strip(),
                        account_name=str(item.get("account_name") or item.get("alias") or "").strip(),
                        account_id=str(item.get("account_id") or item.get("id") or "").strip(),
                        public_key=str(item.get("public_key") or "").strip(),
                        secret_key=str(item.get("secret_key") or "").strip(),
                        base_url=str(item.get("base_url") or base_url).strip().rstrip("/"),
                    )
                )

        valid_accounts = [account for account in accounts if account.company_name and account.account_name and account.secret_key]
        if not valid_accounts:
            raise ValueError(f"Nenhuma credencial Pagar.me valida encontrada em: {credentials_path}")

        return cls(accounts=valid_accounts, base_url=base_url)

    def companies(self) -> list[str]:
        return sorted({account.company_name for account in self._accounts})

    def accounts_for_company(self, company_name: str) -> list[PagarmeAccount]:
        items = [account for account in self._accounts if account.company_name == company_name]
        if not items:
            raise ValueError(f"Empresa '{company_name}' nao encontrada no cadastro do Pagar.me.")
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
