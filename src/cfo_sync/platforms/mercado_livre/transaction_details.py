from __future__ import annotations

import argparse
import json
import socket
import time
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from cfo_sync.core.runtime_paths import default_mercado_livre_credentials_path
from cfo_sync.platforms.mercado_livre.credentials import MercadoLivreCredentialsStore
from cfo_sync.platforms.mercado_livre.oauth import MercadoLivreAPIError, ensure_valid_access_token
from cfo_sync.platforms.mercado_livre.vendas import (
    BASE_URL,
    BILLING_DOCUMENT_TYPE,
    BILLING_PAGE_SIZE,
    MAX_PAGES_SAFETY,
    RETRY_BACKOFF_SECONDS,
    TRANSACTION_DETAIL_MAP_PATH,
)


REGISTRY_PATH = TRANSACTION_DETAIL_MAP_PATH.with_name("transaction_detail_registry.json")
DEFAULT_SPREADSHEET_ID = "1ThLnF-xuovYoILp4rXJl_EoIoPtEC4CDPQ4vpPaBhQQ"
DEFAULT_SHEET_ID = "1851479620"
VALID_CATEGORIES = {
    "Meli Ads",
    "Transporte - Mercadorias vendidas",
    "Tarifas de Marketplace",
    "Fulfillment",
}
DEFAULT_CATEGORY = "Tarifas de Marketplace"


@dataclass(frozen=True)
class SyncResult:
    discovered: int
    inserted: int
    removed: int
    unchanged: int
    pending_review: list[str]


def sync_transaction_detail_map(
    *,
    credentials_path: Path,
    map_path: Path = TRANSACTION_DETAIL_MAP_PATH,
    registry_path: Path = REGISTRY_PATH,
    start_date: str,
    end_date: str,
    clients: list[str] | None = None,
    accounts: list[str] | None = None,
    spreadsheet_id: str | None = None,
    sheet_name: str | None = None,
    sheet_id: str | None = None,
    google_credentials_path: Path | None = None,
    max_pages: int = MAX_PAGES_SAFETY,
) -> SyncResult:
    period_start = date.fromisoformat(start_date)
    period_end = date.fromisoformat(end_date)
    if period_start > period_end:
        raise ValueError("Data inicial nao pode ser maior que data final.")

    existing_map = _load_category_map(map_path)
    existing_registry = _load_registry(registry_path)
    discovered = _discover_transaction_details(
        credentials_path=credentials_path,
        period_start=period_start,
        period_end=period_end,
        clients=clients,
        accounts=accounts,
        max_pages=max_pages,
    )
    if not discovered:
        raise ValueError(
            "Nenhum transaction_detail encontrado na API. "
            "Sincronizacao abortada para evitar apagar o mapeamento atual."
        )

    subtype_categories = _category_by_subtype(existing_registry, existing_map)
    full_scan = max_pages >= MAX_PAGES_SAFETY
    updated_map: dict[str, str] = {} if full_scan else dict(existing_map)
    registry_details: dict[str, dict[str, Any]] = {}
    pending_review: list[str] = []
    inserted = 0

    for detail in sorted(discovered.keys(), key=_normalize_text):
        metadata = discovered[detail]
        category = existing_map.get(detail)
        if category not in VALID_CATEGORIES:
            category = None

        if category is None:
            inserted += 1
            category = _infer_category(
                transaction_detail=detail,
                detail_sub_type=str(metadata.get("detail_sub_type") or ""),
                subtype_categories=subtype_categories,
            )
            if category == DEFAULT_CATEGORY and not _looks_like_marketplace_fee(detail):
                pending_review.append(detail)

        updated_map[detail] = category
        registry_details[detail] = {
            "category": category,
            "detail_sub_type": metadata.get("detail_sub_type") or "",
            "first_seen": metadata.get("first_seen") or "",
            "last_seen": metadata.get("last_seen") or "",
            "count": metadata.get("count") or 0,
            "accounts": sorted(metadata.get("accounts") or []),
        }

    removed = len(set(existing_map.keys()) - set(updated_map.keys())) if full_scan else 0
    unchanged = len(set(existing_map.items()) & set(updated_map.items()))

    _write_json(map_path, updated_map)
    _write_json(
        registry_path,
        {
            "updated_at": date.today().isoformat(),
            "period": {
                "start_date": start_date,
                "end_date": end_date,
            },
            "details": registry_details,
        },
    )

    if spreadsheet_id and (sheet_name or sheet_id):
        if google_credentials_path is None:
            raise ValueError("google_credentials_path e obrigatorio para sincronizar planilha.")
        _sync_google_sheet(
            spreadsheet_id=spreadsheet_id,
            sheet_name=sheet_name,
            sheet_id=sheet_id,
            google_credentials_path=google_credentials_path,
            category_map=updated_map,
        )

    return SyncResult(
        discovered=len(discovered),
        inserted=inserted,
        removed=removed,
        unchanged=unchanged,
        pending_review=pending_review,
    )


def _discover_transaction_details(
    *,
    credentials_path: Path,
    period_start: date,
    period_end: date,
    clients: list[str] | None,
    accounts: list[str] | None,
    max_pages: int,
) -> dict[str, dict[str, Any]]:
    selected_clients = clients or MercadoLivreCredentialsStore.companies(credentials_path)
    if not selected_clients:
        raise ValueError("Nenhum cliente Mercado Livre encontrado nas credenciais.")

    selected_accounts = {
        str(account or "").strip().casefold()
        for account in accounts or []
        if str(account or "").strip()
    }
    discovered: dict[str, dict[str, Any]] = {}

    for client in selected_clients:
        base_store = MercadoLivreCredentialsStore.from_file(credentials_path, company_name=client)
        account_labels = base_store.account_labels or [base_store.auth.account_alias or base_store.auth.user_id]
        for account_label in account_labels:
            if selected_accounts and account_label.casefold() not in selected_accounts:
                continue

            auth = ensure_valid_access_token(
                credentials_path,
                client=client,
                account_alias=account_label,
            )
            account_name = account_label or auth.account_alias or auth.user_id or client
            for month_start in _iter_month_starts(period_start, period_end):
                _collect_month_details(
                    access_token=auth.access_token,
                    account_name=account_name,
                    billing_month_start=month_start,
                    period_start=period_start,
                    period_end=period_end,
                    discovered=discovered,
                    max_pages=max_pages,
                )

    return discovered


def _collect_month_details(
    *,
    access_token: str,
    account_name: str,
    billing_month_start: date,
    period_start: date,
    period_end: date,
    discovered: dict[str, dict[str, Any]],
    max_pages: int,
) -> None:
    path = f"/billing/integration/periods/key/{billing_month_start.isoformat()}/group/ML/details"
    from_id = 0
    page = 0

    while page < max_pages:
        payload = _request_json(
            path=path,
            access_token=access_token,
            params={
                "document_type": BILLING_DOCUMENT_TYPE,
                "limit": str(BILLING_PAGE_SIZE),
                "from_id": str(from_id),
                "sort_by": "DATE",
                "order_by": "DESC",
            },
        )
        results = payload.get("results")
        if not isinstance(results, list) or not results:
            break

        for entry in results:
            charge_info = entry.get("charge_info") if isinstance(entry, dict) else None
            if not isinstance(charge_info, dict):
                continue

            detail = str(charge_info.get("transaction_detail") or "").strip()
            if not detail:
                continue

            created_at = _to_date(charge_info.get("creation_date_time")) or billing_month_start
            if created_at < period_start or created_at > period_end:
                continue

            metadata = discovered.setdefault(
                detail,
                {
                    "detail_sub_type": str(charge_info.get("detail_sub_type") or "").strip(),
                    "first_seen": created_at.isoformat(),
                    "last_seen": created_at.isoformat(),
                    "count": 0,
                    "accounts": set(),
                },
            )
            if not metadata.get("detail_sub_type"):
                metadata["detail_sub_type"] = str(charge_info.get("detail_sub_type") or "").strip()
            metadata["first_seen"] = min(str(metadata["first_seen"]), created_at.isoformat())
            metadata["last_seen"] = max(str(metadata["last_seen"]), created_at.isoformat())
            metadata["count"] = int(metadata["count"]) + 1
            metadata["accounts"].add(account_name)

        last_id = payload.get("last_id")
        if last_id in (None, "", from_id):
            break
        from_id = _to_int(last_id, default=from_id)
        page += 1


def _sync_google_sheet(
    *,
    spreadsheet_id: str,
    sheet_name: str | None,
    sheet_id: str | None,
    google_credentials_path: Path,
    category_map: dict[str, str],
) -> None:
    credentials = Credentials.from_service_account_file(
        str(google_credentials_path),
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
    resolved_sheet_name = _resolve_sheet_name(
        service=service,
        spreadsheet_id=spreadsheet_id,
        sheet_name=sheet_name,
        sheet_id=sheet_id,
    )
    header = [
        "Detalhe",
        "Categoria",
    ]
    rows = [header]
    rows.extend(
        [detail, category]
        for detail, category in sorted(category_map.items(), key=lambda item: _normalize_text(item[0]))
    )

    service.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id,
        range=f"{resolved_sheet_name}!A:B",
        body={},
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{resolved_sheet_name}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": rows},
    ).execute()


def _resolve_sheet_name(
    *,
    service: Any,
    spreadsheet_id: str,
    sheet_name: str | None,
    sheet_id: str | None,
) -> str:
    cleaned_name = str(sheet_name or "").strip()
    if cleaned_name:
        return cleaned_name

    cleaned_id = str(sheet_id or "").strip()
    if not cleaned_id:
        raise ValueError("Informe sheet_name ou sheet_id para sincronizar planilha.")

    try:
        target_gid = int(cleaned_id)
    except ValueError as error:
        raise ValueError(f"sheet_id invalido: {sheet_id}") from error

    metadata = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets(properties(sheetId,title))",
    ).execute()
    for sheet in metadata.get("sheets", []):
        properties = sheet.get("properties", {})
        if properties.get("sheetId") == target_gid:
            title = str(properties.get("title") or "").strip()
            if title:
                return title

    raise ValueError(f"gid {sheet_id} nao encontrado na planilha {spreadsheet_id}.")


def _infer_category(
    *,
    transaction_detail: str,
    detail_sub_type: str,
    subtype_categories: dict[str, str],
) -> str:
    subtype_key = detail_sub_type.strip().casefold()
    if subtype_key and subtype_key in subtype_categories:
        return subtype_categories[subtype_key]

    normalized = _normalize_text(transaction_detail)
    if any(token in normalized for token in ("publicidade", "product ads", "display ads", "brand ads")):
        return "Meli Ads"
    if any(token in normalized for token in ("envio", "mercado envios", "frete", "shipping")):
        return "Transporte - Mercadorias vendidas"
    if any(token in normalized for token in ("full", "fulfillment", "armazenamento", "estoque")):
        return "Fulfillment"
    return DEFAULT_CATEGORY


def _category_by_subtype(
    registry: dict[str, Any],
    category_map: dict[str, str],
) -> dict[str, str]:
    details = registry.get("details")
    if not isinstance(details, dict):
        return {}

    result: dict[str, str] = {}
    for detail, metadata in details.items():
        if not isinstance(metadata, dict):
            continue
        subtype = str(metadata.get("detail_sub_type") or "").strip().casefold()
        category = str(metadata.get("category") or category_map.get(str(detail)) or "").strip()
        if subtype and category in VALID_CATEGORIES:
            result[subtype] = category
    return result


def _load_category_map(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(loaded, dict):
        raise ValueError(f"Mapa invalido em {path}: raiz deve ser objeto JSON.")
    return {
        str(detail).strip(): str(category).strip()
        for detail, category in loaded.items()
        if str(detail).strip() and str(category).strip()
    }


def _load_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(loaded, dict):
        return {}
    return loaded


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _request_json(path: str, access_token: str, params: dict[str, str]) -> dict[str, Any]:
    url = f"{BASE_URL}{path}?{urlencode(params)}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    for backoff in (*RETRY_BACKOFF_SECONDS, None):
        request = Request(url=url, method="GET", headers=headers)
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            body = error.read().decode("utf-8", errors="ignore") if error.fp else ""
            if error.code in {429, 500, 502, 503, 504} and backoff is not None:
                time.sleep(max(60.0, backoff) if error.code == 429 else backoff)
                continue
            raise MercadoLivreAPIError(
                f"Erro HTTP no Mercado Livre (status={error.code}): {body[:300]}"
            ) from error
        except (URLError, TimeoutError, socket.timeout) as error:
            if backoff is not None:
                time.sleep(backoff)
                continue
            raise MercadoLivreAPIError(f"Erro de conexao no Mercado Livre: {error}") from error
        except json.JSONDecodeError as error:
            raise MercadoLivreAPIError("Resposta invalida da API Mercado Livre.") from error

    raise MercadoLivreAPIError("Falha inesperada ao chamar Mercado Livre.")


def _iter_month_starts(period_start: date, period_end: date) -> list[date]:
    current = date(period_start.year, period_start.month, 1)
    last = date(period_end.year, period_end.month, 1)
    months: list[date] = []
    while current <= last:
        months.append(current)
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return months


def _normalize_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    without_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(without_accents.casefold().split())


def _looks_like_marketplace_fee(transaction_detail: str) -> bool:
    normalized = _normalize_text(transaction_detail)
    return any(
        token in normalized
        for token in (
            "custo por vender",
            "custo por cobrar",
            "taxa de parcelamento",
            "tarifa de venda",
            "tarifa por devolucao",
            "processamento",
        )
    )


def _to_date(raw_value: Any) -> date | None:
    text = str(raw_value or "").strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", maxsplit=1)[0]
    elif " " in text:
        text = text.split(" ", maxsplit=1)[0]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _split_csv(value: str | None) -> list[str] | None:
    if value is None:
        return None
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or None


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Sincroniza transaction_detail_map.json com detalhes ativos da API Mercado Livre.",
    )
    parser.add_argument("--credentials", default=str(default_mercado_livre_credentials_path()))
    parser.add_argument("--map", default=str(TRANSACTION_DETAIL_MAP_PATH))
    parser.add_argument("--registry", default=str(REGISTRY_PATH))
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--clients", default=None, help="Clientes separados por virgula.")
    parser.add_argument("--accounts", default=None, help="Aliases/filiais separados por virgula.")
    parser.add_argument("--spreadsheet-id", default=None)
    parser.add_argument("--sheet-name", default=None)
    parser.add_argument("--sheet-id", default=None, help="GID da aba no Google Sheets.")
    parser.add_argument("--google-credentials", default=None)
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES_SAFETY)
    args = parser.parse_args()

    result = sync_transaction_detail_map(
        credentials_path=Path(args.credentials),
        map_path=Path(args.map),
        registry_path=Path(args.registry),
        start_date=args.start_date,
        end_date=args.end_date,
        clients=_split_csv(args.clients),
        accounts=_split_csv(args.accounts),
        spreadsheet_id=args.spreadsheet_id,
        sheet_name=args.sheet_name,
        sheet_id=args.sheet_id,
        google_credentials_path=Path(args.google_credentials) if args.google_credentials else None,
        max_pages=max(1, args.max_pages),
    )
    print(
        "Sync Mercado Livre transaction_detail concluido: "
        f"descobertos={result.discovered} inseridos={result.inserted} "
        f"removidos={result.removed} inalterados={result.unchanged}"
    )
    if result.pending_review:
        print("Novos detalhes inseridos com categoria padrao para revisao:")
        for detail in result.pending_review:
            print(f"- {detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
