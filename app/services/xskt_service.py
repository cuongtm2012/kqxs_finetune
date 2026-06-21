import logging
import re
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup

from app.repositories.draw_repo import draw_repo
from app.utils.http_util import obtain_content
from app.utils.validator import validate_string

logger = logging.getLogger(__name__)

PRIZE_ROWS = ("ĐB", "G1", "G2", "G3", "G4", "G5", "G6", "G7")
XSKT_MB_URL = "https://xskt.com.vn/ket-qua-xo-so-theo-ngay/mien-bac-xsmb/{day}.html"


def xskt_day_url(day_yyyy_mm_dd: str) -> str:
    dt = datetime.strptime(day_yyyy_mm_dd, "%Y-%m-%d")
    return XSKT_MB_URL.format(day=dt.strftime("%d-%m-%Y"))


def parse_xskt_mb(day_yyyy_mm_dd: str) -> tuple[list[str], Optional[str]]:
    """Return (27 prize numbers, station name)."""
    html = obtain_content(xskt_day_url(day_yyyy_mm_dd))
    if not html or "CrowdSec Captcha" in html:
        return [], None

    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.result")
    if not table:
        return [], None

    station = None
    header = table.select_one("tr")
    if header:
        text = header.get_text(" ", strip=True)
        match = re.search(r"\(([^)]+)\)", text)
        if match:
            station = match.group(1)

    prizes: list[str] = []
    for row in table.select("tr"):
        cells = [c.get_text(" ", strip=True) for c in row.select("td")]
        if not cells or cells[0] not in PRIZE_ROWS:
            continue
        prizes.extend(re.findall(r"\d+", cells[1]))

    if len(prizes) < 27:
        logger.warning("xskt %s: expected 27 prizes, got %d", day_yyyy_mm_dd, len(prizes))
        prizes = (prizes + [""] * 27)[:27]
    return prizes[:27], station


def import_mb_from_xskt(day_yyyy_mm_dd: str) -> bool:
    numbers, station = parse_xskt_mb(day_yyyy_mm_dd)
    if not validate_string(numbers[0] if numbers else ""):
        return False
    return draw_repo.upsert_mb_draw(day_yyyy_mm_dd, numbers, station=station, source="xskt")


def parse_draw_date_from_link(link: str) -> Optional[str]:
    """Parse https://xskt.com.vn/xsmb/ngay-20-6-2026 -> 2026-06-20"""
    match = re.search(r"ngay-(\d{1,2})-(\d{1,2})(?:-(\d{4}))?", link or "")
    if not match:
        return None
    day, month, year = match.group(1), match.group(2), match.group(3)
    if not year:
        year = str(datetime.now().year)
    return f"{year}-{int(month):02d}-{int(day):02d}"
