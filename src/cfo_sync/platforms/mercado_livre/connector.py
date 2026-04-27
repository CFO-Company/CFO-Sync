from __future__ import annotations

from pathlib import Path

from cfo_sync.core.models import RawRecord, ResourceConfig
from cfo_sync.core.runtime_paths import default_mercado_livre_credentials_path
from cfo_sync.platforms.mercado_livre.credentials import MercadoLivreCredentialsStore
from cfo_sync.platforms.mercado_livre.vendas import fetch_vendas


class MercadoLivreConnector:
    platform_key = "mercado_livre"

    def __init__(self, credentials_path: Path | None = None) -> None:
        self.credentials_path = credentials_path or default_mercado_livre_credentials_path()

    def fetch(
        self,
        client: str,
        resource: ResourceConfig,
        start_date: str | None = None,
        end_date: str | None = None,
        sub_clients: list[str] | None = None,
    ) -> list[RawRecord]:
        if resource.name != "vendas":
            return []

        selected_aliases = self._resolve_selected_aliases(client=client, sub_clients=sub_clients)
        if not selected_aliases:
            return fetch_vendas(
                client=client,
                resource=resource,
                credentials_path=self.credentials_path,
                start_date=start_date,
                end_date=end_date,
            )

        rows: list[RawRecord] = []
        for alias in selected_aliases:
            rows.extend(
                fetch_vendas(
                    client=client,
                    resource=resource,
                    credentials_path=self.credentials_path,
                    start_date=start_date,
                    end_date=end_date,
                    account_alias=alias,
                    account_label_override=alias,
                )
            )
        return rows

    def _resolve_selected_aliases(
        self,
        *,
        client: str,
        sub_clients: list[str] | None,
    ) -> list[str]:
        if sub_clients:
            selected: list[str] = []
            seen: set[str] = set()
            for raw_alias in sub_clients:
                alias = str(raw_alias or "").strip()
                if not alias:
                    continue
                normalized = alias.casefold()
                if normalized in seen:
                    continue
                seen.add(normalized)
                selected.append(alias)
            if selected:
                return selected

        try:
            store = MercadoLivreCredentialsStore.from_file(
                self.credentials_path,
                company_name=client,
            )
        except (FileNotFoundError, ValueError):
            return []
        return list(store.account_labels)
