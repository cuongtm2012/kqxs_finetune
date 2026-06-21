import logging
import re
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup

from app.repositories.draw_repo import draw_repo
from app.utils.http_util import obtain_content
from app.utils.validator import validate_string

logger = logging.getLogger(__name__)

MINHNGOC_MB_URL = "https://www.minhngoc.net.vn/ket-qua-xo-so/mien-bac/{day}.html"

PRIZE_LABELS = (
    "Giải ĐB",
    "Giải nhất",
    "Giải nhì",
    "Giải ba",
    "Giải tư",
    "Giải năm",
    "Giải sáu",
    "Giải bảy",
)
PRIZE_COUNTS = (1, 1, 2, 6, 4, 6, 3, 4)


def minhngoc_day_url(day_yyyy_mm_dd: str) -> str:
    dt = datetime.strptime(day_yyyy_mm_dd, "%Y-%m-%d")
    return MINHNGOC_MB_URL.format(day=dt.strftime("%d-%m-%Y"))


def _split_concat(text: str, count: int) -> list[str]:
    digits = re.sub(r"\D", "", text)
    if not digits or count <= 0:
        return []
    extra = len(digits) % count
    if extra:
        digits = digits[:-extra]
    if not digits:
        return []
    width = len(digits) // count
    return [digits[i : i + width] for i in range(0, len(digits), width)]


def _extract_station(section_text: str) -> Optional[str]:
    match = re.search(r"Xổ Số\s+([^\-]+)", section_text)
    if match:
        return match.group(1).strip()
    return None


def _parse_section(section: BeautifulSoup, day_yyyy_mm_dd: str) -> tuple[list[str], Optional[str]]:
    dt = datetime.strptime(day_yyyy_mm_dd, "%Y-%m-%d")
    date_marker = dt.strftime("%d/%m/%Y")
    station = None
    prizes: list[str] = []

    for row in section.select("tr"):
        tds = row.select("td")
        if len(tds) < 2:
            continue
        label = tds[0].get_text(strip=True)
        if label not in PRIZE_LABELS:
            if date_marker in row.get_text(" ", strip=True):
                station = _extract_station(row.get_text(" ", strip=True)) or station
            continue

        idx = PRIZE_LABELS.index(label)
        count = PRIZE_COUNTS[idx]
        values = [td.get_text(strip=True) for td in tds[1:] if td.get_text(strip=True).isdigit()]

        if len(values) >= count:
            nums = values[:count]
        elif len(values) == 1:
            nums = _split_concat(values[0], count)
        else:
            nums = []
            for value in values:
                nums.extend(_split_concat(value, 1))
            if len(nums) < count and values:
                nums = _split_concat("".join(values), count)

        if len(nums) != count:
            logger.warning(
                "minhngoc %s %s: expected %d numbers, got %d",
                day_yyyy_mm_dd,
                label,
                count,
                len(nums),
            )
            return [], station
        prizes.extend(nums)

    if len(prizes) != 27:
        return [], station
    return prizes, station


def parse_minhngoc_mb(day_yyyy_mm_dd: str) -> tuple[list[str], Optional[str]]:
    html = obtain_content(minhngoc_day_url(day_yyyy_mm_dd))
    if not html:
        return [], None

    soup = BeautifulSoup(html, "html.parser")
    dt = datetime.strptime(day_yyyy_mm_dd, "%Y-%m-%d")
    date_marker = dt.strftime("%d/%m/%Y")

    for box in soup.select(".box_kqxs"):
        text = box.get_text(" ", strip=True)
        if date_marker not in text:
            continue
        prizes, station = _parse_section(box, day_yyyy_mm_dd)
        if prizes:
            if not station:
                station = _extract_station(text)
            return prizes, station

    return [], None


def import_mb_from_minhngoc(day_yyyy_mm_dd: str) -> bool:
    numbers, station = parse_minhngoc_mb(day_yyyy_mm_dd)
    if not validate_string(numbers[0] if numbers else ""):
        return False
    return draw_repo.upsert_mb_draw(
        day_yyyy_mm_dd, numbers, station=station, source="minhngoc"
    )
