from __future__ import annotations

from cfo_sync.core.models import RawRecord, ResourceConfig
from cfo_sync.platforms.google_ads.api import normalize_period
from cfo_sync.platforms.google_ads.credentials import GoogleAdsAccount, GoogleAdsAuth


def fetch_insights_stub(
    client: str,
    resource: ResourceConfig,
    accounts: list[GoogleAdsAccount],
    auth: GoogleAdsAuth | None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[RawRecord]:
    normalize_period(start_date=start_date, end_date=end_date)
    _ = (client, resource, accounts, auth)
    return []
