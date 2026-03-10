from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from unicodedata import normalize

from cfo_sync.core.models import PlatformConfig, ResourceConfig, SheetTabTarget
from cfo_sync.core.runtime_paths import default_omie_credentials_path


OMIE_DEFAULT_SPREADSHEET_ID = "14W1swSXAdvOzz1A8DwZug02aKRQnhROQyaqr1D2Mq-E"
OMIE_CREDENTIALS_PATH = default_omie_credentials_path()

OMIE_FIELD_MAP = {
    "origem": "Origem",
    "fonte": "Fonte",
    "data": "dDtLanc",
    "conta_corrente": "nCodCC",
    "valor_lancamento": "nValorLanc",
    "departamento": "Departamento",
    "codigo_categoria": "cCodCateg",
    "observacao": "cObs",
    "cliente": "nCodCliente",
    "natureza": "cNatureza",
    "valor_percentual": "ValorPercentual",
    "categoria": "Categoria",
    "departamento_desc": "Departamento_Desc",
    "cliente_desc": "Cliente",
    "valor_sinal": "Valor sinal",
    "data_registro": "Data Registro",
}


@dataclass(frozen=True)
class OmieCredential:
    company_name: str
    alias_name: str
    app_key: str
    app_secret: str
    app_name: str
    include_accounts_payable: bool
    include_accounts_receivable: bool
    gid: str


class OmieCredentialsStore:
    def __init__(self, credentials: list[OmieCredential], spreadsheet_id: str) -> None:
        self._credentials = credentials
        self.spreadsheet_id = spreadsheet_id

    @classmethod
    def from_file(cls, credentials_path: Path) -> "OmieCredentialsStore":
        if not credentials_path.exists():
            raise FileNotFoundError(f"Arquivo de credenciais Omie nao encontrado: {credentials_path}")

        return cls._from_json_file(credentials_path)

    @classmethod
    def _from_json_file(cls, credentials_path: Path) -> "OmieCredentialsStore":
        data = json.loads(credentials_path.read_text(encoding="utf-8-sig"))
        spreadsheet_id = str(data.get("spreadsheet_id") or OMIE_DEFAULT_SPREADSHEET_ID).strip()
        credentials: list[OmieCredential] = []

        for company_name, aliases in data.get("companies", {}).items():
            for item in aliases:
                credentials.append(
                    OmieCredential(
                        company_name=str(company_name).strip(),
                        alias_name=str(
                            item.get("alias")
                            or item.get("alias_name")
                            or item.get("cliente")
                            or ""
                        ).strip(),
                        app_key=str(item.get("app_key") or "").strip(),
                        app_secret=str(item.get("app_secret") or "").strip(),
                        app_name=str(item.get("app_name") or "").strip(),
                        include_accounts_payable=_parse_bool_like(item.get("include_accounts_payable")),
                        include_accounts_receivable=_parse_bool_like(item.get("include_accounts_receivable")),
                        gid=str(item.get("gid") or "").strip(),
                    )
                )

        if not credentials:
            raise ValueError(f"Nenhuma credencial Omie valida encontrada em: {credentials_path}")

        return cls(credentials=credentials, spreadsheet_id=spreadsheet_id)

    def companies(self) -> list[str]:
        return sorted({item.company_name for item in self._credentials})

    def credentials_for_company(self, company_name: str) -> list[OmieCredential]:
        items = [item for item in self._credentials if item.company_name == company_name]
        if not items:
            raise ValueError(f"Empresa '{company_name}' nao encontrada no cadastro da Omie.")
        return items

    def alias_names_for_company(self, company_name: str) -> list[str]:
        seen: set[str] = set()
        names: list[str] = []
        for item in self.credentials_for_company(company_name):
            if item.alias_name in seen:
                continue
            seen.add(item.alias_name)
            names.append(item.alias_name)
        return names

    def gid_for_company(self, company_name: str) -> str:
        gids = [item.gid for item in self.credentials_for_company(company_name) if str(item.gid).strip()]
        if not gids:
            raise ValueError(f"Empresa '{company_name}' nao possui GID configurado na Omie.")
        counts = Counter(gids)
        return counts.most_common(1)[0][0]


def build_omie_platform_config(credentials_path: Path = OMIE_CREDENTIALS_PATH) -> PlatformConfig | None:
    resolved_path = resolve_omie_credentials_path(credentials_path)
    if resolved_path is None:
        return None

    try:
        store = OmieCredentialsStore.from_file(resolved_path)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
    spreadsheet_id = store.spreadsheet_id or OMIE_DEFAULT_SPREADSHEET_ID
    spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
    client_tabs = {
        company_name: SheetTabTarget(
            gid=store.gid_for_company(company_name),
            tab_name="",
            spreadsheet_id=spreadsheet_id,
        )
        for company_name in store.companies()
    }

    resource = ResourceConfig(
        name="financeiro",
        endpoint="/api/v1/financas",
        spreadsheet_url=spreadsheet_url,
        spreadsheet_id=spreadsheet_id,
        field_map=OMIE_FIELD_MAP,
        client_tabs=client_tabs,
    )

    return PlatformConfig(
        key="omie",
        label="Omie",
        clients=store.companies(),
        resources=[resource],
    )


def _parse_yes_no(raw_value: str) -> bool:
    normalized = normalize("NFKD", str(raw_value or "").strip()).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.upper()
    return normalized == "SIM"


def resolve_omie_credentials_path(credentials_path: Path = OMIE_CREDENTIALS_PATH) -> Path | None:
    return credentials_path if credentials_path.exists() else None


def _parse_bool_like(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return _parse_yes_no(str(value or ""))
