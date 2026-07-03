"""Forum collection schedule — mirror extension date-window (Asia/Ho_Chi_Minh)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

COLLECT_START_H = 18
COLLECT_START_M = 30
DEFAULT_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def forum_target_date(
    now: datetime | None = None,
    time_zone: ZoneInfo = DEFAULT_TZ,
) -> str:
    """Ngày quay XSMB: sau 18:30 ICT → ngày mai."""
    now = now or datetime.now(time_zone)
    if now.tzinfo is None:
        now = now.replace(tzinfo=time_zone)
    else:
        now = now.astimezone(time_zone)
    after_start = now.hour > COLLECT_START_H or (
        now.hour == COLLECT_START_H and now.minute >= COLLECT_START_M
    )
    d = now.date()
    if after_start:
        d = d + timedelta(days=1)
    return d.isoformat()
