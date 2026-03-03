from __future__ import annotations

from pathlib import Path
from typing import Any

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from cfo_sync.core.models import RawRecord, ResourceConfig, SheetTabTarget


class GoogleSheetsExporter:
    def __init__(self, credentials_path: Path) -> None:
        self.credentials_path = credentials_path
        self._service = None

    def export(self, client: str, platform_key: str, resource: ResourceConfig, rows: list[RawRecord]) -> int:
        target_tab = resource.client_tabs.get(client)
        if target_tab is None:
            raise ValueError(
                f"Cliente '{client}' nao configurado em {platform_key}/{resource.name} para exportacao."
            )

        if not rows:
            return 0

        spreadsheet_id = target_tab.spreadsheet_id or resource.spreadsheet_id
        tab_name = self._resolve_tab_name(spreadsheet_id, target_tab)
        mapped_rows = [self._map_to_sheet_columns(resource, row) for row in rows]

        if platform_key == "yampi" and resource.name == "financeiro":
            return self._upsert_by_keys(
                spreadsheet_id=spreadsheet_id,
                tab_name=tab_name,
                rows=mapped_rows,
                ordered_columns=list(resource.field_map.values()),
                key_columns=("Data", "Alias"),
            )

        values = [self._to_sheet_row(row, ordered_columns=list(resource.field_map.values())) for row in mapped_rows]
        self._append_rows(
            spreadsheet_id=spreadsheet_id,
            tab_name=tab_name,
            rows=values,
        )

        return len(values)

    def _upsert_by_keys(
        self,
        spreadsheet_id: str,
        tab_name: str,
        rows: list[dict[str, object]],
        ordered_columns: list[str],
        key_columns: tuple[str, str],
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
            if column not in header:
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

        header_index = {column: index for index, column in enumerate(header)}
        key_to_row: dict[tuple[str, str], int] = {}
        for row_number, existing_row in enumerate(existing_values[1:], start=2):
            row_key = self._row_key_from_values(existing_row, header_index, key_columns)
            if row_key is not None:
                key_to_row[row_key] = row_number

        updates: list[dict[str, Any]] = []
        appends: list[list[object]] = []

        for mapped_row in rows:
            row_values = self._to_sheet_row(mapped_row, ordered_columns=header)
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
        gid = int(target_tab.gid)
        for sheet in sheets_metadata.get("sheets", []):
            properties = sheet.get("properties", {})
            if properties.get("sheetId") == gid:
                resolved_title = str(properties.get("title", "")).strip()
                return resolved_title

        raise ValueError(f"gid {target_tab.gid} nao encontrado na planilha {spreadsheet_id}.")

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

    @staticmethod
    def _row_key_from_values(
        values: list[object],
        header_index: dict[str, int],
        key_columns: tuple[str, str],
    ) -> tuple[str, str] | None:
        first_key = GoogleSheetsExporter._safe_get(values, header_index.get(key_columns[0]))
        second_key = GoogleSheetsExporter._safe_get(values, header_index.get(key_columns[1]))

        if not first_key or not second_key:
            return None

        return (first_key, second_key)

    @staticmethod
    def _row_key_from_mapping(
        mapped_row: dict[str, object],
        key_columns: tuple[str, str],
    ) -> tuple[str, str] | None:
        first_key = str(mapped_row.get(key_columns[0], "")).strip()
        second_key = str(mapped_row.get(key_columns[1], "")).strip()
        if not first_key or not second_key:
            return None
        return (first_key, second_key)

    @staticmethod
    def _safe_get(values: list[object], index: int | None) -> str:
        if index is None or index >= len(values):
            return ""
        return str(values[index]).strip()

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
