from __future__ import annotations

import logging
from pathlib import Path

from cfo_sync.core.models import RawRecord, ResourceConfig
from cfo_sync.platforms.mercado_pago.credentials import MercadoPagoCredentialsStore
from cfo_sync.platforms.mercado_pago.financeiro import fetch_financeiro
from cfo_sync.platforms.mercado_pago.oauth import ensure_valid_access_token
from cfo_sync.platforms.mercado_pago.payments import fetch_payments


logger = logging.getLogger(__name__)


class MercadoPagoConnector:
    platform_key = "mercado_pago"

    def __init__(self, credentials_path: Path) -> None:
        self.credentials_path = credentials_path

    def fetch(
        self,
        client: str,
        resource: ResourceConfig,
        start_date: str | None = None,
        end_date: str | None = None,
        sub_clients: list[str] | None = None,
    ) -> list[RawRecord]:
        store = self._load_store()
        if store is None:
            return []

        try:
            accounts = store.accounts_for_company(client)
        except ValueError as error:
            logger.warning("Mercado Pago sem conta para cliente %s: %s", client, error)
            return []

        selected_accounts = self._resolve_selected_accounts(accounts=accounts, sub_clients=sub_clients)
        if not selected_accounts:
            return []
        selected_accounts = [
            ensure_valid_access_token(
                self.credentials_path,
                client=client,
                account_alias=account.account_name,
            )
            for account in selected_accounts
        ]

        if resource.name in {"pagamentos", "payments"}:
            return fetch_payments(
                client=client,
                resource=resource,
                accounts=selected_accounts,
                start_date=start_date,
                end_date=end_date,
                sub_clients=sub_clients,
            )

        if resource.name == "financeiro":
            return fetch_financeiro(
                client=client,
                resource=resource,
                accounts=selected_accounts,
                start_date=start_date,
                end_date=end_date,
                sub_clients=sub_clients,
            )

        return []

    def _load_store(self) -> MercadoPagoCredentialsStore | None:
        try:
            return MercadoPagoCredentialsStore.from_file(self.credentials_path)
        except (FileNotFoundError, ValueError, KeyError, TypeError) as error:
            logger.warning("Mercado Pago indisponivel: %s", error)
            return None

    @staticmethod
    def _resolve_selected_accounts(
        *,
        accounts: list,
        sub_clients: list[str] | None,
    ) -> list:
        if not sub_clients:
            return accounts

        selected_names = {name.strip() for name in sub_clients if name and str(name).strip()}
        if not selected_names:
            return []

        return [account for account in accounts if account.account_name in selected_names]
