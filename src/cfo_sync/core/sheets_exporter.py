from __future__ import annotations

from datetime import date, datetime
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from cfo_sync.core.models import RawRecord, ResourceConfig, SheetTabTarget


class GoogleSheetsExporter:
    def __init__(self, credentials_path: Path) -> None:
        self.credentials_path = credentials_path
        self._service = None

    def export(
        self,
        client: str,
        platform_key: str,
        resource: ResourceConfig,
        rows: list[RawRecord],
        start_date: str | None = None,
        end_date: str | None = None,
        sub_clients: list[str] | None = None,
    ) -> int:
        target_tab = self._resolve_client_tab(resource=resource, client=client)
        if target_tab is None:
            available_clients = ", ".join(sorted(resource.client_tabs.keys()))
            raise ValueError(
                f"Cliente '{client}' nao configurado em {platform_key}/{resource.name} para exportação. "
                f"Clientes disponiveis: {available_clients}."
            )

        spreadsheet_id = target_tab.spreadsheet_id or resource.spreadsheet_id
        tab_name = self._resolve_tab_name(spreadsheet_id, target_tab)
        mapped_rows = [self._map_to_sheet_columns(resource, row) for row in rows]
        ordered_columns = list(resource.field_map.values())

        period_column = self._resolve_period_column(resource)
        replaced_by_period = self._replace_month_period_rows(
            spreadsheet_id=spreadsheet_id,
            tab_name=tab_name,
            resource=resource,
            rows=mapped_rows,
            ordered_columns=ordered_columns,
            period_column=period_column,
            start_date=start_date,
            end_date=end_date,
            sub_clients=sub_clients,
        )
        if replaced_by_period:
            return len(mapped_rows)

        if platform_key.startswith("omie") and resource.name == "financeiro":
            return self._upsert_by_keys(
                spreadsheet_id=spreadsheet_id,
                tab_name=tab_name,
                rows=mapped_rows,
                ordered_columns=ordered_columns,
                key_columns=tuple(resource.field_map.values()),
            )

        if not rows:
            return 0

        if platform_key == "yampi" and resource.name == "financeiro":
            return self._upsert_by_keys(
                spreadsheet_id=spreadsheet_id,
                tab_name=tab_name,
                rows=mapped_rows,
                ordered_columns=ordered_columns,
                key_columns=("Data", "Alias"),
            )

        if platform_key == "mercado_livre" and resource.name == "vendas":
            return self._upsert_by_keys(
                spreadsheet_id=spreadsheet_id,
                tab_name=tab_name,
                rows=mapped_rows,
                ordered_columns=ordered_columns,
                key_columns=("Mês/Ano", "Conta"),
            )

        if platform_key == "tiktok_ads" and resource.name in {"campanhas", "insights", "contas"}:
            return self._upsert_by_keys(
                spreadsheet_id=spreadsheet_id,
                tab_name=tab_name,
                rows=mapped_rows,
                ordered_columns=ordered_columns,
                key_columns=("Mês/Ano", "Conta"),
            )

        if platform_key == "google_ads" and resource.name in {"contas", "insights", "campanhas"}:
            key_columns = self._resolve_google_ads_key_columns(resource)
            if key_columns:
                return self._upsert_by_keys(
                    spreadsheet_id=spreadsheet_id,
                    tab_name=tab_name,
                    rows=mapped_rows,
                    ordered_columns=ordered_columns,
                    key_columns=key_columns,
                )

        values = [self._to_sheet_row(row, ordered_columns=ordered_columns) for row in mapped_rows]
        self._append_rows(
            spreadsheet_id=spreadsheet_id,
            tab_name=tab_name,
            rows=values,
        )

        return len(values)

    def _replace_month_period_rows(
        self,
        spreadsheet_id: str,
        tab_name: str,
        resource: ResourceConfig,
        rows: list[dict[str, object]],
        ordered_columns: list[str],
        period_column: str | None,
        start_date: str | None,
        end_date: str | None,
        sub_clients: list[str] | None,
    ) -> bool:
        if not period_column or not start_date or not end_date:
            return False

        period_start = self._parse_iso_date(start_date)
        period_end = self._parse_iso_date(end_date)
        if period_start is None or period_end is None or period_start > period_end:
            return False
        target_month_years = self._month_years_in_period(start_date=start_date, end_date=end_date)
        period_is_monthly = period_column == str(resource.field_map.get("mes_ano") or "").strip()
        scope_filters = self._resolve_period_scope_filters(resource=resource, sub_clients=sub_clients)

        service = self._get_service()
        read_response = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"{tab_name}!A:ZZ",
        ).execute()
        existing_values = read_response.get("values", [])

        if not existing_values:
            if not rows:
                return True
            all_values = [ordered_columns] + [self._to_sheet_row(row, ordered_columns) for row in rows]
            self._ensure_grid_capacity(
                spreadsheet_id=spreadsheet_id,
                tab_name=tab_name,
                required_rows=len(all_values),
                required_columns=len(ordered_columns),
            )
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"{tab_name}!A1",
                valueInputOption="USER_ENTERED",
                body={"values": all_values},
            ).execute()
            return True

        header = [str(value) for value in existing_values[0]]
        if period_column not in header and len(existing_values) > 1:
            if self._resolve_header_column(header, period_column) is None:
                return False
        header_changed = False
        for column in ordered_columns:
            if self._resolve_header_column(header, column) is None:
                header.append(column)
                header_changed = True

        if header_changed:
            self._ensure_grid_capacity(
                spreadsheet_id=spreadsheet_id,
                tab_name=tab_name,
                required_rows=1,
                required_columns=len(header),
            )
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"{tab_name}!1:1",
                valueInputOption="USER_ENTERED",
                body={"values": [header]},
            ).execute()

        resolved_period_column = self._resolve_header_column(header, period_column)
        if resolved_period_column is None:
            return False

        resolved_scope_filters = self._resolve_scope_filters_for_header(
            header=header,
            scope_filters=scope_filters,
        )
        period_column_index = header.index(resolved_period_column)
        header_index = {column: index for index, column in enumerate(header)}
        rows_to_delete: list[int] = []
        for row_number, existing_row in enumerate(existing_values[1:], start=2):
            raw_value = self._safe_get(existing_row, period_column_index)
            if period_is_monthly:
                row_in_period = self._extract_month_year(raw_value) in target_month_years
            else:
                row_date = self._extract_date(raw_value)
                row_in_period = row_date is not None and period_start <= row_date <= period_end
            if row_in_period:
                if self._row_matches_scope_filters(
                    values=existing_row,
                    header_index=header_index,
                    scope_filters=resolved_scope_filters,
                ):
                    rows_to_delete.append(row_number)

        if rows_to_delete:
            self._delete_rows_by_numbers(
                spreadsheet_id=spreadsheet_id,
                tab_name=tab_name,
                row_numbers=rows_to_delete,
            )

        if rows:
            appends = [
                self._to_sheet_row_for_header(
                    mapped_row=mapped_row,
                    header=header,
                    ordered_columns=ordered_columns,
                )
                for mapped_row in rows
            ]
            self._append_rows(
                spreadsheet_id=spreadsheet_id,
                tab_name=tab_name,
                rows=appends,
            )

        return True

    def _delete_rows_by_numbers(
        self,
        spreadsheet_id: str,
        tab_name: str,
        row_numbers: list[int],
    ) -> None:
        if not row_numbers:
            return

        sheet_properties = self._get_sheet_properties_by_title(
            spreadsheet_id=spreadsheet_id,
            tab_name=tab_name,
        )
        sheet_id = int(sheet_properties.get("sheetId"))
        requests = [
            {
                "deleteDimension": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "ROWS",
                        "startIndex": row_number - 1,
                        "endIndex": row_number,
                    }
                }
            }
            for row_number in sorted(set(row_numbers), reverse=True)
            if row_number > 1
        ]

        if not requests:
            return

        self._get_service().spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests},
        ).execute()

    @staticmethod
    def _month_years_in_period(start_date: str, end_date: str) -> set[tuple[int, int]]:
        try:
            start = date.fromisoformat(start_date)
            end = date.fromisoformat(end_date)
        except ValueError:
            return set()

        if start > end:
            return set()

        month_years: set[tuple[int, int]] = set()
        current = date(start.year, start.month, 1)
        last = date(end.year, end.month, 1)
        while current <= last:
            month_years.add((current.month, current.year))
            if current.month == 12:
                current = date(current.year + 1, 1, 1)
            else:
                current = date(current.year, current.month + 1, 1)
        return month_years

    @staticmethod
    def _resolve_period_scope_filters(
        resource: ResourceConfig,
        sub_clients: list[str] | None,
    ) -> dict[str, set[str]]:
        if not sub_clients:
            return {}

        selected_values = {
            str(value).strip().casefold() for value in sub_clients if str(value).strip()
        }
        if not selected_values:
            return {}

        for api_field in (
            "alias",
            "origem",
            "conta",
            "account_name",
            "nome_ca",
            "customer_name",
        ):
            column_name = str(resource.field_map.get(api_field) or "").strip()
            if column_name:
                return {column_name: selected_values}

        return {}

    @staticmethod
    def _row_matches_scope_filters(
        values: list[object],
        header_index: dict[str, int],
        scope_filters: dict[str, set[str]],
    ) -> bool:
        if not scope_filters:
            return True

        for column_name, allowed_values in scope_filters.items():
            column_index = header_index.get(column_name)
            if column_index is None:
                return False
            raw_value = GoogleSheetsExporter._safe_get(values, column_index)
            if raw_value.casefold() not in allowed_values:
                return False
        return True

    @classmethod
    def _resolve_scope_filters_for_header(
        cls,
        header: list[str],
        scope_filters: dict[str, set[str]],
    ) -> dict[str, set[str]]:
        if not scope_filters:
            return {}

        resolved: dict[str, set[str]] = {}
        for column_name, allowed_values in scope_filters.items():
            resolved_column = cls._resolve_header_column(header, column_name)
            if resolved_column is None:
                resolved[column_name] = allowed_values
            else:
                resolved[resolved_column] = allowed_values
        return resolved

    @staticmethod
    def _extract_month_year(raw_value: str) -> tuple[int, int] | None:
        text = str(raw_value or "").strip()
        if not text:
            return None

        month_year_match = re.fullmatch(r"(\d{1,2})/(\d{4})", text)
        if month_year_match:
            month = int(month_year_match.group(1))
            year = int(month_year_match.group(2))
            if 1 <= month <= 12:
                return month, year

        br_date_match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
        if br_date_match:
            month = int(br_date_match.group(2))
            year = int(br_date_match.group(3))
            if 1 <= month <= 12:
                return month, year

        iso_date_match = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
        if iso_date_match:
            year = int(iso_date_match.group(1))
            month = int(iso_date_match.group(2))
            if 1 <= month <= 12:
                return month, year

        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return parsed.month, parsed.year
        except ValueError:
            return None

    @staticmethod
    def _extract_date(raw_value: str) -> date | None:
        text = str(raw_value or "").strip()
        if not text:
            return None

        br_date_match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
        if br_date_match:
            day = int(br_date_match.group(1))
            month = int(br_date_match.group(2))
            year = int(br_date_match.group(3))
            try:
                return date(year, month, day)
            except ValueError:
                return None

        iso_date_match = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
        if iso_date_match:
            year = int(iso_date_match.group(1))
            month = int(iso_date_match.group(2))
            day = int(iso_date_match.group(3))
            try:
                return date(year, month, day)
            except ValueError:
                return None

        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            return None

    @staticmethod
    def _parse_iso_date(raw_value: str) -> date | None:
        try:
            return date.fromisoformat(str(raw_value or "").strip())
        except ValueError:
            return None

    @staticmethod
    def _resolve_period_column(resource: ResourceConfig) -> str | None:
        for api_field in ("mes_ano", "data", "data_gasto", "date"):
            column_name = str(resource.field_map.get(api_field) or "").strip()
            if column_name:
                return column_name
        return None

    def _upsert_by_keys(
        self,
        spreadsheet_id: str,
        tab_name: str,
        rows: list[dict[str, object]],
        ordered_columns: list[str],
        key_columns: tuple[str, ...],
    ) -> int:
        service = self._get_service()
        read_response = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"{tab_name}!A:Z",
        ).execute()
        existing_values = read_response.get("values", [])

        if not existing_values:
            all_values = [ordered_columns] + [self._to_sheet_row(row, ordered_columns) for row in rows]
            self._ensure_grid_capacity(
                spreadsheet_id=spreadsheet_id,
                tab_name=tab_name,
                required_rows=len(all_values),
                required_columns=len(ordered_columns),
            )
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"{tab_name}!A1",
                valueInputOption="USER_ENTERED",
                body={"values": all_values},
            ).execute()
            return len(rows)

        header = [str(value) for value in existing_values[0]]
        header_changed = False
        for column in ordered_columns:
            if self._resolve_header_column(header, column) is None:
                header.append(column)
                header_changed = True

        if header_changed:
            self._ensure_grid_capacity(
                spreadsheet_id=spreadsheet_id,
                tab_name=tab_name,
                required_rows=1,
                required_columns=len(header),
            )
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"{tab_name}!1:1",
                valueInputOption="USER_ENTERED",
                body={"values": [header]},
            ).execute()

        resolved_key_columns = tuple(
            self._resolve_header_column(header, column) or column for column in key_columns
        )
        header_index = {column: index for index, column in enumerate(header)}
        key_to_row: dict[tuple[str, ...], int] = {}
        for row_number, existing_row in enumerate(existing_values[1:], start=2):
            row_key = self._row_key_from_values(existing_row, header_index, resolved_key_columns)
            if row_key is not None:
                key_to_row[row_key] = row_number

        updates: list[dict[str, Any]] = []
        appends: list[list[object]] = []

        for mapped_row in rows:
            row_values = self._to_sheet_row_for_header(
                mapped_row=mapped_row,
                header=header,
                ordered_columns=ordered_columns,
            )
            row_key = self._row_key_from_mapping(mapped_row, key_columns)

            if row_key is not None and row_key in key_to_row:
                updates.append(
                    {
                        "range": f"{tab_name}!A{key_to_row[row_key]}",
                        "values": [row_values],
                    }
                )
            else:
                appends.append(row_values)

        if updates:
            service.spreadsheets().values().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={
                    "valueInputOption": "USER_ENTERED",
                    "data": updates,
                },
            ).execute()

        if appends:
            self._append_rows(
                spreadsheet_id=spreadsheet_id,
                tab_name=tab_name,
                rows=appends,
                start_row=self._next_row_index(existing_values, anchor_column_index=0),
            )

        return len(rows)

    def _append_rows(
        self,
        spreadsheet_id: str,
        tab_name: str,
        rows: list[list[object]],
        start_row: int | None = None,
    ) -> None:
        if not rows:
            return

        service = self._get_service()
        if start_row is None:
            existing = service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=f"{tab_name}!A:A",
            ).execute()
            start_row = self._next_row_index(existing.get("values", []), anchor_column_index=0)

        max_columns = max((len(row) for row in rows), default=1)
        self._ensure_grid_capacity(
            spreadsheet_id=spreadsheet_id,
            tab_name=tab_name,
            required_rows=start_row + len(rows) - 1,
            required_columns=max_columns,
        )

        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{tab_name}!A{start_row}",
            valueInputOption="USER_ENTERED",
            body={"values": rows},
        ).execute()

    def _ensure_grid_capacity(
        self,
        spreadsheet_id: str,
        tab_name: str,
        required_rows: int,
        required_columns: int,
    ) -> None:
        service = self._get_service()
        sheet_properties = self._get_sheet_properties_by_title(
            spreadsheet_id=spreadsheet_id,
            tab_name=tab_name,
        )

        sheet_id = int(sheet_properties.get("sheetId"))
        grid = sheet_properties.get("gridProperties", {})
        current_rows = int(grid.get("rowCount") or 0)
        current_columns = int(grid.get("columnCount") or 0)

        target_rows = max(1, required_rows)
        target_columns = max(1, required_columns)

        requests: list[dict[str, Any]] = []
        if target_rows > current_rows:
            requests.append(
                {
                    "appendDimension": {
                        "sheetId": sheet_id,
                        "dimension": "ROWS",
                        "length": target_rows - current_rows,
                    }
                }
            )

        if target_columns > current_columns:
            requests.append(
                {
                    "appendDimension": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "length": target_columns - current_columns,
                    }
                }
            )

        if not requests:
            return

        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests},
        ).execute()

    def _get_service(self):
        if self._service is not None:
            return self._service

        if not self.credentials_path.exists():
            raise FileNotFoundError(
                f"Arquivo de credencial Google Sheets nao encontrado: {self.credentials_path}"
            )

        credentials = Credentials.from_service_account_file(
            str(self.credentials_path),
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        self._service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
        return self._service

    def _resolve_tab_name(self, spreadsheet_id: str, target_tab: SheetTabTarget) -> str:
        sheets_metadata = (
            self._get_service()
            .spreadsheets()
            .get(spreadsheetId=spreadsheet_id, fields="sheets(properties(sheetId,title))")
            .execute()
        )

        # GID (sheetId) e a fonte de verdade para identificar a aba de destino.
        gid_text = str(target_tab.gid).strip()
        if gid_text:
            try:
                gid = int(gid_text)
            except ValueError:
                gid = None
            if gid is not None:
                for sheet in sheets_metadata.get("sheets", []):
                    properties = sheet.get("properties", {})
                    if properties.get("sheetId") == gid:
                        resolved_title = str(properties.get("title", "")).strip()
                        return resolved_title

        # Fallback: quando o GID nao esta atualizado na configuracao, usa o nome da aba.
        fallback_tab_name = str(target_tab.tab_name).strip()
        if fallback_tab_name:
            return fallback_tab_name

        raise ValueError(
            f"gid {target_tab.gid} nao encontrado na planilha {spreadsheet_id} "
            "e tab_name nao foi informado."
        )

    def _get_sheet_properties_by_title(self, spreadsheet_id: str, tab_name: str) -> dict[str, Any]:
        metadata = (
            self._get_service()
            .spreadsheets()
            .get(
                spreadsheetId=spreadsheet_id,
                fields="sheets(properties(sheetId,title,gridProperties(rowCount,columnCount)))",
            )
            .execute()
        )

        normalized_title = tab_name.strip()
        for sheet in metadata.get("sheets", []):
            properties = sheet.get("properties", {})
            title = str(properties.get("title", "")).strip()
            if title == normalized_title:
                return properties

        raise ValueError(f"Aba '{tab_name}' nao encontrada na planilha {spreadsheet_id}.")

    @staticmethod
    def _map_to_sheet_columns(resource: ResourceConfig, row: RawRecord) -> dict[str, object]:
        return {
            sheet_column: row.get(api_field)
            for api_field, sheet_column in resource.field_map.items()
        }

    @staticmethod
    def _to_sheet_row(mapped_row: dict[str, object], ordered_columns: list[str]) -> list[object]:
        return [mapped_row.get(column) for column in ordered_columns]

    @classmethod
    def _to_sheet_row_for_header(
        cls,
        mapped_row: dict[str, object],
        header: list[str],
        ordered_columns: list[str],
    ) -> list[object]:
        normalized_mapped_columns = {
            cls._normalize_column_label(column): column
            for column in ordered_columns
            if cls._normalize_column_label(column)
        }
        values: list[object] = []
        for header_column in header:
            if header_column in mapped_row:
                values.append(mapped_row.get(header_column))
                continue

            mapped_column = normalized_mapped_columns.get(cls._normalize_column_label(header_column))
            values.append(mapped_row.get(mapped_column) if mapped_column else None)
        return values

    @staticmethod
    def _row_key_from_values(
        values: list[object],
        header_index: dict[str, int],
        key_columns: tuple[str, ...],
    ) -> tuple[str, ...] | None:
        parts = [GoogleSheetsExporter._safe_get(values, header_index.get(column)) for column in key_columns]
        if any(not part for part in parts):
            return None
        return tuple(parts)

    @staticmethod
    def _row_key_from_mapping(
        mapped_row: dict[str, object],
        key_columns: tuple[str, ...],
    ) -> tuple[str, ...] | None:
        parts = [str(mapped_row.get(column, "")).strip() for column in key_columns]
        if any(not part for part in parts):
            return None
        return tuple(parts)

    @staticmethod
    def _safe_get(values: list[object], index: int | None) -> str:
        if index is None or index >= len(values):
            return ""
        return str(values[index]).strip()

    @classmethod
    def _resolve_header_column(cls, header: list[str], column_name: str) -> str | None:
        if column_name in header:
            return column_name

        normalized_column = cls._normalize_column_label(column_name)
        if not normalized_column:
            return None

        matches = [
            header_column
            for header_column in header
            if cls._normalize_column_label(header_column) == normalized_column
        ]
        if len(matches) == 1:
            return matches[0]
        return None

    @staticmethod
    def _normalize_column_label(value: str) -> str:
        without_diacritics = "".join(
            char
            for char in unicodedata.normalize("NFKD", str(value or ""))
            if not unicodedata.combining(char)
        )
        normalized = without_diacritics.casefold()
        normalized = re.sub(r"[^a-z0-9]+", "", normalized)
        return normalized

    @staticmethod
    def _next_row_index(
        existing_values: list[list[object]],
        anchor_column_index: int = 0,
    ) -> int:
        last_non_empty_row = 0
        for row_number, row_values in enumerate(existing_values, start=1):
            if anchor_column_index < len(row_values) and str(row_values[anchor_column_index]).strip():
                last_non_empty_row = row_number
        return last_non_empty_row + 1

    @staticmethod
    def _resolve_google_ads_key_columns(resource: ResourceConfig) -> tuple[str, ...]:
        # Padrao oficial do layout Google Ads no Sheets.
        official_keys: list[str] = []
        for api_field in ("data_gasto", "nome_ca", "nome_campanha", "nome_anuncio"):
            column_name = str(resource.field_map.get(api_field) or "").strip()
            if not column_name or column_name in official_keys:
                continue
            official_keys.append(column_name)
        if len(official_keys) >= 2:
            return tuple(official_keys)

        # Compatibilidade com layouts antigos configurados com chaves em ingles.
        fallback_keys: list[str] = []
        for api_field in ("date", "customer_id", "campaign_id"):
            column_name = str(resource.field_map.get(api_field) or "").strip()
            if not column_name or column_name in fallback_keys:
                continue
            fallback_keys.append(column_name)
        if len(fallback_keys) >= 2:
            return tuple(fallback_keys)

        return ()

    @classmethod
    def _resolve_client_tab(cls, resource: ResourceConfig, client: str) -> SheetTabTarget | None:
        direct_match = resource.client_tabs.get(client)
        if direct_match is not None:
            return direct_match

        normalized_client = cls._normalize_client_name(client)
        normalized_matches = [
            tab
            for configured_client, tab in resource.client_tabs.items()
            if cls._normalize_client_name(configured_client) == normalized_client
        ]
        if len(normalized_matches) == 1:
            return normalized_matches[0]
        if len(normalized_matches) > 1:
            return None

        best_candidate: tuple[float, SheetTabTarget] | None = None
        second_best_score = 0.0
        for configured_client, tab in resource.client_tabs.items():
            score = SequenceMatcher(
                None,
                normalized_client,
                cls._normalize_client_name(configured_client),
            ).ratio()
            if best_candidate is None or score > best_candidate[0]:
                if best_candidate is not None:
                    second_best_score = best_candidate[0]
                best_candidate = (score, tab)
            elif score > second_best_score:
                second_best_score = score

        if best_candidate is None:
            return None

        best_score = best_candidate[0]
        if best_score < 0.86:
            return None

        if best_score - second_best_score < 0.03:
            return None

        return best_candidate[1]

    @staticmethod
    def _normalize_client_name(value: str) -> str:
        without_diacritics = "".join(
            char
            for char in unicodedata.normalize("NFKD", value)
            if not unicodedata.combining(char)
        )
        normalized = without_diacritics.casefold().replace("?", "")
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
        return re.sub(r"\s+", " ", normalized).strip()
