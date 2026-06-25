"""Load historical max cycle data crawled from mketqua.net."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

_DATA_PATH = Path(__file__).resolve().parent / "max_cycle_history.json"


@lru_cache(maxsize=1)
def load_max_cycle_history() -> dict[str, dict]:
    """Return {loto: {max_gap_days, max_gap_start, max_gap_end, source_url}}."""
    if not _DATA_PATH.is_file():
        return {}
    raw = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    numbers = raw.get("numbers", raw)
    if not isinstance(numbers, dict):
        return {}
    out: dict[str, dict] = {}
    for lot, entry in numbers.items():
        if isinstance(entry, dict) and entry.get("max_gap_days"):
            out[str(lot).zfill(2)] = entry
    return out


def get_max_gap_days(loto: str) -> Optional[int]:
    entry = load_max_cycle_history().get(loto.zfill(2))
    if not entry:
        return None
    days = entry.get("max_gap_days")
    return int(days) if days else None
