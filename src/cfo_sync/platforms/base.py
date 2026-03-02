from __future__ import annotations

from typing import Protocol

from cfo_sync.core.models import RawRecord, ResourceConfig


class PlatformConnector(Protocol):
    platform_key: str

    def fetch(
        self,
        client: str,
        resource: ResourceConfig,
        start_date: str | None = None,
        end_date: str | None = None,
        sub_clients: list[str] | None = None,
    ) -> list[RawRecord]:
        ...
