import logging
import re
from datetime import date, datetime
from typing import Optional

logger = logging.getLogger(__name__)

# SPEC weekday: 0=Chủ nhật, 1=Thứ hai, ..., 6=Thứ bảy
SPEC_WEEKDAY_LABELS = (
    "Chủ nhật",
    "Thứ hai",
    "Thứ ba",
    "Thứ tư",
    "Thứ năm",
    "Thứ sáu",
    "Thứ bảy",
)

_SPEC_TO_PYTHON = {0: 6, 1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5}
_PYTHON_TO_SPEC = {v: k for k, v in _SPEC_TO_PYTHON.items()}


def spec_weekday_to_python(spec_weekday: int) -> int:
    return _SPEC_TO_PYTHON[spec_weekday]


def python_weekday_to_spec(python_weekday: int) -> int:
    return _PYTHON_TO_SPEC[python_weekday]


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
