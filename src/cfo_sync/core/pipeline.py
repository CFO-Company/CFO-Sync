from __future__ import annotations

from pathlib import Path

from cfo_sync.core.db import LocalDatabase
from cfo_sync.core.models import AppConfig
from cfo_sync.core.sheets_exporter import GoogleSheetsExporter
from cfo_sync.platforms.registry import build_platform_registry


class SyncPipeline:
    def __init__(
        self,
        config: AppConfig,
        omie_credentials_path: Path | None = None,
    ) -> None:
        self.config = config
        self.db = LocalDatabase(config.database_path)
        self.db.initialize()
        credentials_path = config.credentials_dir / config.google_sheets.credentials_file
        self.exporter = GoogleSheetsExporter(credentials_path=credentials_path)
        yampi_credentials_path = config.credentials_dir / config.yampi.credentials_file
        meta_ads_credentials_path = config.credentials_dir / config.meta_ads.credentials_file
        google_ads_credentials_path = config.credentials_dir / config.google_ads.credentials_file
        tiktok_ads_credentials_path = config.credentials_dir / config.tiktok_ads.credentials_file
        tiktok_shop_credentials_path = config.credentials_dir / config.tiktok_shop.credentials_file
        resolved_omie_2026_credentials_path = omie_credentials_path or (
            config.credentials_dir / "omie_credentials.json"
        )
        resolved_omie_2025_credentials_path = config.credentials_dir / "omie_2025.json"
        resolved_omie_cfo_credentials_path = config.credentials_dir / "omie_cfo.json"
        mercado_livre_credentials_path = config.credentials_dir / "mercado_livre_credentials.json"
        self.connectors = build_platform_registry(
            yampi_credentials_path=yampi_credentials_path,
            meta_ads_credentials_path=meta_ads_credentials_path,
            google_ads_credentials_path=google_ads_credentials_path,
            tiktok_ads_credentials_path=tiktok_ads_credentials_path,
            tiktok_shop_credentials_path=tiktok_shop_credentials_path,
            omie_2026_credentials_path=resolved_omie_2026_credentials_path,
            omie_2025_credentials_path=resolved_omie_2025_credentials_path,
            omie_cfo_credentials_path=resolved_omie_cfo_credentials_path,
            mercado_livre_credentials_path=mercado_livre_credentials_path,
        )

    def collect(
        self,
        platform_key: str,
        client: str,
        start_date: str | None = None,
        end_date: str | None = None,
        resource_names: list[str] | None = None,
        sub_clients: list[str] | None = None,
        sub_client: str | None = None,
    ) -> int:
        platform = next((p for p in self.config.platforms if p.key == platform_key), None)
        if platform is None:
            raise ValueError(f"Plataforma nao encontrada: {platform_key}")

        connector = self.connectors[platform_key]
        resolved_sub_clients = sub_clients or ([sub_client] if sub_client else None)
        total_rows = 0
        for resource in self._resolve_resources(platform.resources, resource_names):
            rows = connector.fetch(
                client=client,
                resource=resource,
                start_date=start_date,
                end_date=end_date,
                sub_clients=resolved_sub_clients,
            )
            for row in rows:
                self.db.save(client=client, platform=platform_key, resource=resource.name, payload=row)
            total_rows += len(rows)
        return total_rows

    def export_to_sheets(
        self,
        platform_key: str,
        client: str,
        start_date: str | None = None,
        end_date: str | None = None,
        resource_names: list[str] | None = None,
        sub_clients: list[str] | None = None,
        sub_client: str | None = None,
    ) -> int:
        platform = next((p for p in self.config.platforms if p.key == platform_key), None)
        if platform is None:
            raise ValueError(f"Plataforma nao encontrada: {platform_key}")

        connector = self.connectors[platform_key]
        resolved_sub_clients = sub_clients or ([sub_client] if sub_client else None)
        exported = 0
        for resource in self._resolve_resources(platform.resources, resource_names):
            rows = connector.fetch(
                client=client,
                resource=resource,
                start_date=start_date,
                end_date=end_date,
                sub_clients=resolved_sub_clients,
            )
            exported += self.exporter.export(
                client=client,
                platform_key=platform_key,
                resource=resource,
                rows=rows,
                start_date=start_date,
                end_date=end_date,
                sub_clients=resolved_sub_clients,
            )
        return exported

    @staticmethod
    def _resolve_resources(resources, resource_names: list[str] | None):
        if not resource_names:
            return resources

        selected = [resource for resource in resources if resource.name in resource_names]
        if not selected:
            raise ValueError("Nenhum recurso valido selecionado para esta plataforma.")
        return selected
