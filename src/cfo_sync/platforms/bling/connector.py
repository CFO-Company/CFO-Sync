from __future__ import annotations

import logging
from pathlib import Path

from cfo_sync.core.models import RawRecord, ResourceConfig
from cfo_sync.platforms.bling.api import fetch_paginated_rows, flatten_record
from cfo_sync.platforms.bling.credentials import BlingAccount, BlingCredentialsStore
from cfo_sync.platforms.bling.oauth import refresh_bling_access_token


logger = logging.getLogger(__name__)


class BlingConnector:
    platform_key = "bling"

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
            logger.warning("Bling sem conta para cliente %s: %s", client, error)
            return []

        if sub_clients:
            selected = {name.strip() for name in sub_clients if name.strip()}
            accounts = [account for account in accounts if account.account_name in selected]
        if not accounts:
            return []

        rows: list[RawRecord] = []
        active_store = store
        for account in accounts:
            active_store, active_account = self._ensure_account_token(active_store, account)
            page_rows = fetch_paginated_rows(
                endpoint=resource.endpoint,
                access_token=active_account.access_token,
                start_date=start_date,
                end_date=end_date,
            )
            for raw_row in page_rows:
                mapped = flatten_record(raw_row)
                mapped["cliente"] = client
                mapped["conta"] = active_account.account_name
                mapped["account_name"] = active_account.account_name
                rows.append(mapped)
        return rows

    def _load_store(self) -> BlingCredentialsStore | None:
        try:
            return BlingCredentialsStore.from_file(self.credentials_path)
        except (FileNotFoundError, ValueError, KeyError, TypeError) as error:
            logger.warning("Bling indisponivel: %s", error)
            return None

    def _ensure_account_token(
        self,
        store: BlingCredentialsStore,
        account: BlingAccount,
    ) -> tuple[BlingCredentialsStore, BlingAccount]:
        if not store.access_token_expired(account):
            return store, account
        if not store.auth.client_id or not store.auth.client_secret or not account.refresh_token:
            return store, account

        token_payload = refresh_bling_access_token(
            client_id=store.auth.client_id,
            client_secret=store.auth.client_secret,
            refresh_token=account.refresh_token,
        )
        updated_store = store.with_updated_account_tokens(
            account,
            access_token=str(token_payload.get("access_token") or ""),
            refresh_token=str(token_payload.get("refresh_token") or account.refresh_token),
            token_type=str(token_payload.get("token_type") or account.token_type),
            expires_in=_parse_int(token_payload.get("expires_in"), default=account.expires_in),
        )
        updated_store.save()
        updated_account = next(
            item
            for item in updated_store.accounts_for_company(account.company_name)
            if item.account_name.casefold() == account.account_name.casefold()
        )
        return updated_store, updated_account


def _parse_int(value: object, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
