from __future__ import annotations

from datetime import datetime
from typing import Tuple

import dateparser
from dateparser.search import search_dates


def parse_explicit_datetime(value: str | None, timezone_name: str) -> int | None:
    # This helper is for CLI flags like --start and --end.
    if not value:
        return None
    parsed = dateparser.parse(
        value,
        settings={
            "TIMEZONE": timezone_name,
            "RETURN_AS_TIMEZONE_AWARE": False,
        },
    )
    return None if parsed is None else int(parsed.timestamp())


def parse_local_time_window(
    query: str,
    timezone_name: str,
    now: datetime,
) -> Tuple[int | None, int | None, list[str]]:
    # OCR-only mode should stay local, so we do a best-effort parse here without Gemini.
    # This is intentionally conservative.
    matches = search_dates(
        query,
        settings={
            "TIMEZONE": timezone_name,
            "RELATIVE_BASE": now,
            "RETURN_AS_TIMEZONE_AWARE": False,
        },
    )

    if not matches:
        return None, None, []

    datetimes = [match[1] for match in matches]
    if len(datetimes) >= 2 and "between" in query.lower():
        start_dt, end_dt = datetimes[0], datetimes[1]
        start_epoch = int(start_dt.timestamp())
        end_epoch = int(end_dt.timestamp())
        return start_epoch, end_epoch, ["local time window parsed from query"]

    if len(datetimes) >= 1:
        only = datetimes[0]
        start_epoch = int(only.timestamp())
        end_epoch = int(only.timestamp()) + 3600
        return start_epoch, end_epoch, ["local approximate time parsed from query"]

    return None, None, []
