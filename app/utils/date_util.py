import logging
import re
from datetime import date, datetime
from typing import Optional

logger = logging.getLogger(__name__)


def today_yyyy_mm_dd() -> str:
    return date.today().strftime("%Y-%m-%d")


def format_yyyy_mm_dd(value) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    return value.strftime("%Y-%m-%d")


def normalize_ngaychot(ngaychot: Optional[str]) -> Optional[str]:
    if not ngaychot or not ngaychot.strip():
        return ngaychot
    value = ngaychot.strip()
    try:
        if re.fullmatch(r"\d{2}-\d{2}-\d{4}", value):
            return datetime.strptime(value, "%d-%m-%Y").strftime("%Y-%m-%d")
        if re.fullmatch(r"\d{2}/\d{2}/\d{4}", value):
            return datetime.strptime(value, "%d/%m/%Y").strftime("%Y-%m-%d")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return value
    except ValueError as exc:
        logger.warning("Could not normalize ngaychot '%s': %s", value, exc)
    return value


def normalize_ngaychot_regional(ngaychot: Optional[str]) -> Optional[str]:
    if not ngaychot or not ngaychot.strip():
        return ngaychot
    value = ngaychot.strip()
    try:
        parsed = None
        if re.fullmatch(r"\d{2}-\d{2}-\d{4}", value):
            parsed = datetime.strptime(value, "%d-%m-%Y")
        elif re.fullmatch(r"\d{2}/\d{2}/\d{4}", value):
            parsed = datetime.strptime(value, "%d/%m/%Y")
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            parsed = datetime.strptime(value, "%Y-%m-%d")
        if parsed:
            return parsed.strftime("%d/%m")
    except ValueError as exc:
        logger.warning("Could not normalize regional ngaychot '%s': %s", value, exc)
    return value
