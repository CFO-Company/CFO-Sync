from __future__ import annotations

from datetime import date


class GoogleAdsAPIError(RuntimeError):
    pass


def normalize_period(
    start_date: str | None,
    end_date: str | None,
) -> tuple[str | None, str | None]:
    if not start_date or not end_date:
        return start_date, end_date

    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if start > end:
        raise ValueError("Periodo invalido para Google ADS: data inicial maior que data final.")
    return start.isoformat(), end.isoformat()
