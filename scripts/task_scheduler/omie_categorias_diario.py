from __future__ import annotations

import argparse
import logging
import sys
import traceback
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from cfo_sync.core.config_loader import load_app_config
from cfo_sync.core.models import SheetTabTarget
from cfo_sync.core.runtime_paths import app_config_path, ensure_runtime_layout
from cfo_sync.core.sheets_exporter import GoogleSheetsExporter
from cfo_sync.platforms.omie.api import call_omie_api
from cfo_sync.platforms.omie.credentials import OmieCredential, OmieCredentialsStore


DEFAULT_SPREADSHEET_ID = "14W1swSXAdvOzz1A8DwZug02aKRQnhROQyaqr1D2Mq-E"
DEFAULT_GID = "2087624295"
DEFAULT_CREDENTIAL_FILES = ("omie_credentials.json",)

COLUMNS = [
    "origem",
    "codigo",
    "descricao",
    "natureza",
    "tipo_categoria",
    "codigo_dre",
    "data_atualizacao",
]


@dataclass(frozen=True)
class CategoryRow:
    origem: str
    codigo: str
    descricao: str
    natureza: str
    tipo_categoria: str
    codigo_dre: str

    @property
    def key(self) -> tuple[str, str]:
        return (_normalize_key(self.origem), _normalize_key(self.codigo))

    def comparable_values(self) -> tuple[str, str, str, str, str, str]:
        return (
            self.origem.strip(),
            self.codigo.strip(),
            self.descricao.strip(),
            self.natureza.strip(),
            self.tipo_categoria.strip(),
            self.codigo_dre.strip(),
        )


def _build_logger(log_dir: Path) -> tuple[logging.Logger, Path]:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"omie_categorias_{date.today().isoformat()}.log"
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    logger = logging.getLogger(f"cfo_sync.automation.omie_categorias.{run_id}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | run=%(run_id)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    class RunIdFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            record.run_id = run_id
            return True

    run_filter = RunIdFilter()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(run_filter)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.addFilter(run_filter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    return logger, log_path


def _paginate_categories(credential: OmieCredential) -> list[dict[str, Any]]:
    page = 1
    total_pages = 1
    rows: list[dict[str, Any]] = []

    while page <= total_pages:
        response = call_omie_api(
            credential=credential,
            call="ListarCategorias",
            endpoint="geral/categorias/",
            params={
                "pagina": page,
                "registros_por_pagina": 500,
            },
        )
        if not response:
            break

        rows.extend([item for item in response.get("categoria_cadastro") or [] if isinstance(item, dict)])
        total_pages = int(response.get("total_de_paginas") or 1)
        page += 1

    return rows


def _category_from_payload(credential: OmieCredential, payload: dict[str, Any]) -> CategoryRow | None:
    codigo = _first_non_empty(
        payload,
        ("codigo", "cCodCateg", "codigo_categoria", "cod_categoria"),
    )
    if not codigo:
        return None

    return CategoryRow(
        origem=str(credential.app_name or credential.alias_name or credential.company_name).strip(),
        codigo=codigo,
        descricao=_first_non_empty(payload, ("descricao", "cDescricao", "desc_categoria")),
        natureza=_first_non_empty(payload, ("natureza", "cNatureza")),
        tipo_categoria=_first_non_empty(payload, ("tipo_categoria", "tipo", "cTipo")),
        codigo_dre=_first_non_empty(
            payload,
            ("codigo_dre", "codigoDRE", "codDRE", "cCodDRE", "codigo_dre_omie"),
        ),
    )


def _fetch_categories(credentials: list[OmieCredential], logger: logging.Logger) -> list[CategoryRow]:
    rows: list[CategoryRow] = []

    for credential in credentials:
        origem = str(credential.app_name or credential.alias_name or credential.company_name).strip()
        logger.info("FETCH_START origem=%s empresa=%s alias=%s", origem, credential.company_name, credential.alias_name)
        payloads = _paginate_categories(credential)
        logger.info("FETCH_OK origem=%s categorias=%s", origem, len(payloads))

        for payload in payloads:
            row = _category_from_payload(credential, payload)
            if row is None:
                continue
            rows.append(row)

    return sorted(
        rows,
        key=lambda item: (
            item.origem.casefold(),
            _category_code_sort_key(item.codigo),
            item.descricao.casefold(),
            item.natureza.casefold(),
            item.codigo_dre.casefold(),
        ),
    )


def _load_credentials(config_credentials_dir: Path, credential_files: list[str]) -> list[OmieCredential]:
    credentials: list[OmieCredential] = []
    missing_files: list[Path] = []

    for file_name in credential_files:
        path = Path(file_name)
        if not path.is_absolute():
            path = config_credentials_dir / path
        if not path.exists():
            missing_files.append(path)
            continue

        store = OmieCredentialsStore.from_file(path)
        for company in store.companies():
            credentials.extend(store.credentials_for_company(company))

    if not credentials:
        missing_text = ", ".join(str(path) for path in missing_files)
        raise ValueError(f"Nenhuma credencial Omie encontrada. Arquivos ausentes: {missing_text}")

    return credentials


def _read_sheet(service: Any, spreadsheet_id: str, tab_name: str) -> list[list[object]]:
    response = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{tab_name}!A:Z",
    ).execute()
    return response.get("values", [])


def _sync_sheet(
    exporter: GoogleSheetsExporter,
    spreadsheet_id: str,
    gid: str,
    categories: list[CategoryRow],
) -> dict[str, int]:
    service = exporter._get_service()
    tab_name = exporter._resolve_tab_name(
        spreadsheet_id=spreadsheet_id,
        target_tab=SheetTabTarget(gid=gid, tab_name=""),
    )
    existing_values = _read_sheet(service, spreadsheet_id=spreadsheet_id, tab_name=tab_name)
    timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    existing_by_key: dict[tuple[str, str], list[dict[str, str]]] = {}
    if existing_values:
        header = [str(value).strip() for value in existing_values[0]]
        header_index = {_normalize_header(column): index for index, column in enumerate(header)}
        for row in existing_values[1:]:
            origem = _safe_get(row, header_index.get("origem"))
            codigo = _safe_get(row, header_index.get("codigo"))
            if not origem or not codigo:
                continue
            key = (_normalize_key(origem), _normalize_key(codigo))
            existing_by_key.setdefault(key, []).append({
                "origem": origem,
                "codigo": codigo,
                "descricao": _safe_get(row, header_index.get("descricao")),
                "natureza": _safe_get(row, header_index.get("natureza")),
                "tipo_categoria": _safe_get(row, header_index.get("tipo_categoria")),
                "codigo_dre": _safe_get(row, header_index.get("codigo_dre")),
                "data_atualizacao": _safe_get(row, header_index.get("data_atualizacao")),
            })

    created = 0
    updated = 0
    unchanged = 0
    used_existing_ids: set[int] = set()
    rows: list[list[object]] = [COLUMNS]

    for category in categories:
        existing = _pop_matching_existing(
            candidates=existing_by_key.get(category.key, []),
            category=category,
            used_existing_ids=used_existing_ids,
        )
        if existing is None:
            created += 1
            update_date = timestamp
        elif _existing_comparable_values(existing) != category.comparable_values():
            updated += 1
            update_date = timestamp
        else:
            unchanged += 1
            update_date = existing.get("data_atualizacao") or timestamp

        rows.append(
            [
                category.origem,
                category.codigo,
                category.descricao,
                category.natureza,
                category.tipo_categoria,
                category.codigo_dre,
                update_date,
            ]
        )

    existing_count = sum(len(items) for items in existing_by_key.values())
    removed = max(0, existing_count - len(used_existing_ids))

    exporter._ensure_grid_capacity(
        spreadsheet_id=spreadsheet_id,
        tab_name=tab_name,
        required_rows=max(len(rows), len(existing_values), 1),
        required_columns=len(COLUMNS),
    )
    service.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id,
        range=f"{tab_name}!A:Z",
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{tab_name}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": rows},
    ).execute()

    return {
        "total": len(categories),
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "removed": removed,
    }


def _run(
    log_dir: Path,
    spreadsheet_id: str,
    gid: str,
    credential_files: list[str],
) -> int:
    ensure_runtime_layout()
    logger, log_path = _build_logger(log_dir=log_dir)
    run_start = perf_counter()

    logger.info(
        "RUN_START script=omie_categorias_diario python=%s log=%s spreadsheet_id=%s gid=%s",
        sys.version.split()[0],
        str(log_path),
        spreadsheet_id,
        gid,
    )

    config = load_app_config(app_config_path())
    credentials = _load_credentials(config.credentials_dir, credential_files)
    logger.info("CREDENCIAIS arquivos=%s contas=%s", ",".join(credential_files), len(credentials))

    categories = _fetch_categories(credentials, logger)
    google_credentials_path = config.credentials_dir / config.google_sheets.credentials_file
    exporter = GoogleSheetsExporter(credentials_path=google_credentials_path)
    stats = _sync_sheet(
        exporter=exporter,
        spreadsheet_id=spreadsheet_id,
        gid=gid,
        categories=categories,
    )

    elapsed = perf_counter() - run_start
    logger.info(
        "RUN_END status=ok total=%s criadas=%s atualizadas=%s inalteradas=%s removidas=%s tempo_total=%.2fs",
        stats["total"],
        stats["created"],
        stats["updated"],
        stats["unchanged"],
        stats["removed"],
        elapsed,
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Atualiza diariamente a planilha de categorias da Omie.",
    )
    parser.add_argument(
        "--spreadsheet-id",
        default=DEFAULT_SPREADSHEET_ID,
        help="ID da planilha de destino.",
    )
    parser.add_argument(
        "--gid",
        default=DEFAULT_GID,
        help="GID da aba de categorias.",
    )
    parser.add_argument(
        "--credentials-file",
        action="append",
        default=None,
        help=(
            "Arquivo de credenciais Omie dentro de credentials_dir. "
            "Pode ser informado mais de uma vez. Padrao: omie_credentials.json."
        ),
    )
    parser.add_argument(
        "--log-dir",
        default="logs/automation",
        help="Diretorio de logs (padrao: logs/automation).",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    log_dir = Path(args.log_dir)
    if not log_dir.is_absolute():
        log_dir = (PROJECT_ROOT / log_dir).resolve()

    credential_files = args.credentials_file or list(DEFAULT_CREDENTIAL_FILES)

    try:
        return _run(
            log_dir=log_dir,
            spreadsheet_id=args.spreadsheet_id,
            gid=args.gid,
            credential_files=credential_files,
        )
    except Exception as error:  # noqa: BLE001
        print(f"FALHA FATAL: {error}", file=sys.stderr)
        traceback.print_exc()
        return 1


def _first_non_empty(payload: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _safe_get(values: list[object], index: int | None) -> str:
    if index is None or index >= len(values):
        return ""
    return str(values[index]).strip()


def _normalize_header(value: str) -> str:
    return str(value or "").strip().casefold()


def _normalize_key(value: str) -> str:
    return str(value or "").strip().casefold()


def _existing_comparable_values(existing: dict[str, str]) -> tuple[str, str, str, str, str, str]:
    return (
        existing.get("origem", "").strip(),
        existing.get("codigo", "").strip(),
        existing.get("descricao", "").strip(),
        existing.get("natureza", "").strip(),
        existing.get("tipo_categoria", "").strip(),
        existing.get("codigo_dre", "").strip(),
    )


def _pop_matching_existing(
    candidates: list[dict[str, str]],
    category: CategoryRow,
    used_existing_ids: set[int],
) -> dict[str, str] | None:
    exact_match: dict[str, str] | None = None
    fallback_match: dict[str, str] | None = None

    for candidate in candidates:
        candidate_id = id(candidate)
        if candidate_id in used_existing_ids:
            continue

        if fallback_match is None:
            fallback_match = candidate

        if _existing_comparable_values(candidate) == category.comparable_values():
            exact_match = candidate
            break

    selected = exact_match or fallback_match
    if selected is not None:
        used_existing_ids.add(id(selected))
    return selected


def _category_code_sort_key(value: str) -> tuple[int, tuple[int, ...] | str]:
    parts = str(value or "").strip().split(".")
    try:
        return (0, tuple(int(part) for part in parts if part != ""))
    except ValueError:
        return (1, str(value or "").strip())


if __name__ == "__main__":
    raise SystemExit(main())
