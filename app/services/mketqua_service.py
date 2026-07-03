"""Fetch XSMB results from mketqua.net (available ~18:31 ICT daily)."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Optional

from app.repositories.draw_repo import draw_repo
from app.utils.date_util import normalize_ngaychot
from app.utils.http_util import obtain_content
from app.utils.validator import validate_string

logger = logging.getLogger(__name__)

MKETQUA_HOME = "https://mketqua.net/"
MKETQUA_RAW_URL = "http://data.ketqua1.net/kq-mb.raw"

# rs_{level}_{order} — 8 prize levels, 27 numbers total (MB)
_MB_LEVEL_COUNTS = (1, 1, 2, 6, 4, 6, 3, 4)


def _parse_rs_elements(html: str) -> list[str]:
    """Parse div#rs_{level}_{order} blocks from mketqua live result table."""
    pattern = re.compile(
        r'id="rs_(\d+)_(\d+)"[^>]*rs_len="(\d+)"[^>]*>(\d+)<',
        re.I,
    )
    slots: dict[tuple[int, int], str] = {}
    for m in pattern.finditer(html):
        level = int(m.group(1))
        order = int(m.group(2))
        slots[(level, order)] = m.group(4)

    if len(slots) < 27:
        return []

    numbers: list[str] = []
    for level, count in enumerate(_MB_LEVEL_COUNTS):
        for order in range(count):
            num = slots.get((level, order))
            if not num:
                logger.warning("mketqua missing rs_%s_%s", level, order)
                return []
            numbers.append(num)
    return numbers


def _parse_draw_date(html: str) -> Optional[str]:
    m = re.search(
        r"ngày\s+(\d{1,2}-\d{1,2}-\d{4})",
        html,
        re.I,
    )
    if m:
        return normalize_ngaychot(m.group(1))
    m = re.search(r"(\d{4}-\d{2}-\d{2})", html)
    if m:
        return m.group(1)
    return None


def parse_mketqua_mb(html: str, expected_day: Optional[str] = None) -> tuple[list[str], Optional[str], Optional[str]]:
    """Return (27 prize numbers, station label, draw_date yyyy-mm-dd)."""
    numbers = _parse_rs_elements(html)
    if len(numbers) != 27:
        return [], None, None

    draw_date = _parse_draw_date(html)
    if expected_day and draw_date and draw_date != expected_day:
        logger.warning("mketqua date mismatch: page=%s expected=%s", draw_date, expected_day)
        return [], None, draw_date

    station = "Truyền Thống"
    return numbers, station, draw_date


def fetch_mketqua_html(day_yyyy_mm_dd: Optional[str] = None) -> str:
    html = obtain_content(MKETQUA_HOME) or ""
    if html and _parse_rs_elements(html):
        return html

    raw = obtain_content(MKETQUA_RAW_URL) or ""
    if raw and day_yyyy_mm_dd:
        # Fallback: concatenate digits blob (legacy ketqua raw feed)
        digits = re.sub(r"\D", "", raw.split()[-1] if raw.split() else raw)
        if len(digits) >= 100:
            return raw
    return html


def import_mb_from_mketqua(day_yyyy_mm_dd: str) -> bool:
    html = fetch_mketqua_html(day_yyyy_mm_dd)
    numbers, station, page_date = parse_mketqua_mb(html, expected_day=day_yyyy_mm_dd)
    if not numbers:
        return False
    if page_date and page_date != day_yyyy_mm_dd:
        logger.info("mketqua import skipped: page date %s != %s", page_date, day_yyyy_mm_dd)
        return False
    if not validate_string(numbers[0]):
        return False
    return draw_repo.upsert_mb_draw(
        day_yyyy_mm_dd,
        numbers,
        station=station,
        source="mketqua",
    )
