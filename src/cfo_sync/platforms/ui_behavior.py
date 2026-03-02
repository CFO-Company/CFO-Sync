from __future__ import annotations

from datetime import date

from cfo_sync.core.models import RawRecord


class PlatformUIBehavior:
    def __init__(self, platform_key: str) -> None:
        self.platform_key = platform_key

    @property
    def supports_sku_workflow(self) -> bool:
        return False

    def companies(self, configured_clients: list[str]) -> list[str]:
        return configured_clients

    def sub_client_names(self, company_name: str) -> list[str]:
        return []

    def uses_dedicated_resource_tab(self, resource_name: str) -> bool:
        return False

    def normalize_period(
        self,
        resource_name: str,
        start_date: date,
        end_date: date,
        today: date,
    ) -> tuple[date, date]:
        return start_date, end_date

    def search_sku_rows(
        self,
        company_name: str,
        order_number: str,
        selected_sub_clients: list[str] | None,
    ) -> tuple[list[RawRecord], list[str]]:
        raise ValueError(f"Busca SKU nao disponivel para plataforma: {self.platform_key}")
