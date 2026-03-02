from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class YampiAliasCredential:
    alias: str
    user_token: str
    user_secret_key: str


class YampiCredentialsStore:
    def __init__(self, companies: dict[str, list[YampiAliasCredential]]) -> None:
        self._companies = companies

    @classmethod
    def from_file(cls, credentials_path: Path) -> "YampiCredentialsStore":
        if not credentials_path.exists():
            raise FileNotFoundError(f"Arquivo de credenciais Yampi nao encontrado: {credentials_path}")

        data = json.loads(credentials_path.read_text(encoding="utf-8-sig"))
        companies: dict[str, list[YampiAliasCredential]] = {}

        for company_name, aliases in data["companies"].items():
            companies[company_name] = [
                YampiAliasCredential(
                    alias=item["alias"],
                    user_token=item["user_token"],
                    user_secret_key=item["user_secret_key"],
                )
                for item in aliases
            ]

        return cls(companies=companies)

    def aliases_for_company(self, company_name: str) -> list[YampiAliasCredential]:
        aliases = self._companies.get(company_name)
        if aliases is None:
            raise ValueError(f"Empresa '{company_name}' nao encontrada no arquivo de credenciais da Yampi.")
        return aliases

    def alias_names_for_company(self, company_name: str) -> list[str]:
        return [item.alias for item in self.aliases_for_company(company_name)]

    def companies(self) -> list[str]:
        return sorted(self._companies.keys())
