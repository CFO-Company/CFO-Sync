from __future__ import annotations

import argparse
import sys
import traceback
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from cfo_sync.platforms.mercado_livre.transaction_details import (
    DEFAULT_SHEET_ID,
    DEFAULT_SPREADSHEET_ID,
    sync_transaction_detail_map,
)


def _default_period() -> tuple[str, str]:
    today = date.today()
    start = today.replace(day=1)
    return start.isoformat(), today.isoformat()


def _build_parser() -> argparse.ArgumentParser:
    default_start, default_end = _default_period()
    parser = argparse.ArgumentParser(
        description=(
            "Atualiza transaction_detail_map.json pela API Mercado Livre e sincroniza "
            "a aba De-Para no Google Sheets."
        )
    )
    parser.add_argument(
        "--credentials",
        default=str(PROJECT_ROOT / "secrets" / "mercado_livre_credentials.json"),
    )
    parser.add_argument(
        "--map",
        default=str(
            PROJECT_ROOT
            / "src"
            / "cfo_sync"
            / "platforms"
            / "mercado_livre"
            / "transaction_detail_map.json"
        ),
    )
    parser.add_argument(
        "--registry",
        default=str(
            PROJECT_ROOT
            / "src"
            / "cfo_sync"
            / "platforms"
            / "mercado_livre"
            / "transaction_detail_registry.json"
        ),
    )
    parser.add_argument("--start-date", default=default_start)
    parser.add_argument("--end-date", default=default_end)
    parser.add_argument("--clients", default=None, help="Clientes separados por virgula.")
    parser.add_argument("--accounts", default=None, help="Aliases/filiais separados por virgula.")
    parser.add_argument("--spreadsheet-id", default=DEFAULT_SPREADSHEET_ID)
    parser.add_argument("--sheet-id", default=DEFAULT_SHEET_ID)
    parser.add_argument(
        "--google-credentials",
        default=str(Path.home() / "AppData" / "Local" / "CFO-Sync" / "secrets" / "google_service_account.json"),
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Use apenas para teste parcial. Com esse limite, nao remove detalhes antigos.",
    )
    return parser


def _split_csv(value: str | None) -> list[str] | None:
    if value is None:
        return None
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or None


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        kwargs = {
            "credentials_path": Path(args.credentials),
            "map_path": Path(args.map),
            "registry_path": Path(args.registry),
            "start_date": args.start_date,
            "end_date": args.end_date,
            "clients": _split_csv(args.clients),
            "accounts": _split_csv(args.accounts),
            "spreadsheet_id": args.spreadsheet_id,
            "sheet_id": args.sheet_id,
            "google_credentials_path": Path(args.google_credentials),
        }
        if args.max_pages is not None:
            kwargs["max_pages"] = max(1, args.max_pages)

        result = sync_transaction_detail_map(**kwargs)
    except Exception as error:  # noqa: BLE001
        print(f"FALHA: {error}", file=sys.stderr)
        traceback.print_exc()
        return 1

    print("Sync De-Para Mercado Livre concluido.")
    print(f"Detalhes encontrados: {result.discovered}")
    print(f"Inseridos: {result.inserted}")
    print(f"Removidos: {result.removed}")
    print(f"Inalterados: {result.unchanged}")
    if result.pending_review:
        print("Inseridos com categoria padrao para revisao:")
        for detail in result.pending_review:
            print(f"- {detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
