"""Feature extraction from PostgreSQL history."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

from app.db import fetch_all
from app.prediction.constants import (
    ALL_DIGITS,
    ALL_LOTOS,
    TARGET_DAU,
    TARGET_DE,
    TARGET_DIT,
    TARGET_LOTO,
)

logger = logging.getLogger(__name__)

_cache: Dict[Tuple[str, str], "FeatureContext"] = {}


@dataclass
class DayRecord:
    draw_date: date
    loto_hits: Dict[str, int]
    loto_set: Set[str]
    de: str
    dau_digits: List[str]
    dit_digits: List[str]
    weekday: int


@dataclass
class FeatureContext:
    as_of_date: date
    target_type: str
    target_date: date
    days: List[DayRecord] = field(default_factory=list)

    @property
    def train_days(self) -> int:
        return len(self.days)

    @property
    def last_day(self) -> Optional[DayRecord]:
        return self.days[-1] if self.days else None

    @property
    def universe(self) -> List[str]:
        if self.target_type in (TARGET_DAU, TARGET_DIT):
            return ALL_DIGITS
        return ALL_LOTOS

    @property
    def total_opportunities(self) -> int:
        if self.target_type == TARGET_DE:
            return len(self.days)
        if self.target_type == TARGET_DAU:
            return sum(len(d.dau_digits) for d in self.days)
        if self.target_type == TARGET_DIT:
            return sum(len(d.dit_digits) for d in self.days)
        return len(self.days) * 27

    def hit_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {v: 0 for v in self.universe}
        if self.target_type == TARGET_LOTO:
            for day in self.days:
                for loto, cnt in day.loto_hits.items():
                    counts[loto] = counts.get(loto, 0) + cnt
        elif self.target_type == TARGET_DE:
            for day in self.days:
                counts[day.de] = counts.get(day.de, 0) + 1
        elif self.target_type == TARGET_DAU:
            for day in self.days:
                for d in day.dau_digits:
                    counts[d] = counts.get(d, 0) + 1
        elif self.target_type == TARGET_DIT:
            for day in self.days:
                for d in day.dit_digits:
                    counts[d] = counts.get(d, 0) + 1
        return counts

    def last_seen(self) -> Dict[str, Optional[date]]:
        seen: Dict[str, Optional[date]] = {v: None for v in self.universe}
        if self.target_type == TARGET_LOTO:
            for day in self.days:
                for loto in day.loto_set:
                    seen[loto] = day.draw_date
        elif self.target_type == TARGET_DE:
            for day in self.days:
                seen[day.de] = day.draw_date
        elif self.target_type == TARGET_DAU:
            for day in self.days:
                for d in set(day.dau_digits):
                    seen[d] = day.draw_date
        elif self.target_type == TARGET_DIT:
            for day in self.days:
                for d in set(day.dit_digits):
                    seen[d] = day.draw_date
        return seen

    def weekday_hit_counts(self, weekday: int) -> Tuple[Dict[str, int], int]:
        counts: Dict[str, int] = {v: 0 for v in self.universe}
        opp = 0
        for day in self.days:
            if day.weekday != weekday:
                continue
            if self.target_type == TARGET_LOTO:
                opp += 27
                for loto, cnt in day.loto_hits.items():
                    counts[loto] = counts.get(loto, 0) + cnt
            elif self.target_type == TARGET_DE:
                opp += 1
                counts[day.de] = counts.get(day.de, 0) + 1
            elif self.target_type == TARGET_DAU:
                opp += len(day.dau_digits)
                for d in day.dau_digits:
                    counts[d] = counts.get(d, 0) + 1
            elif self.target_type == TARGET_DIT:
                opp += len(day.dit_digits)
                for d in day.dit_digits:
                    counts[d] = counts.get(d, 0) + 1
        return counts, opp

    @classmethod
    def load(
        cls,
        as_of_date: date,
        target_type: str,
        target_date: Optional[date] = None,
        use_cache: bool = True,
    ) -> "FeatureContext":
        target_date = target_date or (as_of_date + timedelta(days=1))
        key = (as_of_date.isoformat(), target_type)
        if use_cache and key in _cache:
            ctx = _cache[key]
            ctx.target_date = target_date
            return ctx

        days = _load_day_records(as_of_date)
        ctx = cls(as_of_date=as_of_date, target_type=target_type, target_date=target_date, days=days)
        if use_cache:
            _cache[key] = ctx
        return ctx

    @classmethod
    def from_days(
        cls,
        all_days: List[DayRecord],
        as_of_date: date,
        target_type: str,
        target_date: date,
    ) -> "FeatureContext":
        idx = 0
        for i, day in enumerate(all_days):
            if day.draw_date <= as_of_date:
                idx = i + 1
            else:
                break
        return cls(
            as_of_date=as_of_date,
            target_type=target_type,
            target_date=target_date,
            days=all_days[:idx],
        )


def clear_feature_cache() -> None:
    _cache.clear()


def _parse_date(value) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value)[:10])


def _load_day_records(as_of_date: date) -> List[DayRecord]:
    rows = fetch_all(
        """
        SELECT
            d.draw_date,
            p.slot_index,
            p.last_two,
            p.first_digit,
            p.last_digit
        FROM draws d
        JOIN prizes p ON p.draw_id = d.id
        WHERE d.region = 'MB' AND d.draw_date <= %s
        ORDER BY d.draw_date, p.slot_index
        """,
        (as_of_date.isoformat(),),
    )
    by_date: Dict[date, DayRecord] = {}
    for row in rows:
        draw_date = _parse_date(row["draw_date"])
        if draw_date not in by_date:
            by_date[draw_date] = DayRecord(
                draw_date=draw_date,
                loto_hits={},
                loto_set=set(),
                de="",
                dau_digits=[],
                dit_digits=[],
                weekday=draw_date.weekday(),
            )
        rec = by_date[draw_date]
        loto = row["last_two"]
        rec.loto_hits[loto] = rec.loto_hits.get(loto, 0) + 1
        rec.loto_set.add(loto)
        if row["slot_index"] == 0:
            rec.de = loto
        if row["first_digit"] is not None:
            rec.dau_digits.append(str(row["first_digit"]))
        if row["last_digit"] is not None:
            rec.dit_digits.append(str(row["last_digit"]))

    return [by_date[k] for k in sorted(by_date.keys())]


def load_all_day_records() -> List[DayRecord]:
    row = fetch_all(
        "SELECT MAX(draw_date)::text AS newest FROM draws WHERE region = 'MB'",
    )
    if not row or not row[0].get("newest"):
        return []
    newest = date.fromisoformat(row[0]["newest"])
    return _load_day_records(newest)


def draw_dates_between(start: date, end: date) -> List[date]:
    rows = fetch_all(
        """
        SELECT draw_date::text AS d
        FROM draws
        WHERE region = 'MB' AND draw_date >= %s AND draw_date <= %s
        ORDER BY draw_date
        """,
        (start.isoformat(), end.isoformat()),
    )
    return [date.fromisoformat(r["d"]) for r in rows]


def latest_draw_date() -> Optional[date]:
    row = fetch_all("SELECT MAX(draw_date)::text AS d FROM draws WHERE region = 'MB'")
    if not row or not row[0].get("d"):
        return None
    return date.fromisoformat(row[0]["d"])


def previous_draw_date(before: date) -> Optional[date]:
    row = fetch_all(
        """
        SELECT MAX(draw_date)::text AS d
        FROM draws
        WHERE region = 'MB' AND draw_date < %s
        """,
        (before.isoformat(),),
    )
    if not row or not row[0].get("d"):
        return None
    return date.fromisoformat(row[0]["d"])


def actual_values_for_date(draw_date: date, target_type: str) -> Set[str]:
    rows = fetch_all(
        """
        SELECT p.slot_index, p.last_two, p.first_digit, p.last_digit
        FROM draws d
        JOIN prizes p ON p.draw_id = d.id
        WHERE d.region = 'MB' AND d.draw_date = %s
        ORDER BY p.slot_index
        """,
        (draw_date.isoformat(),),
    )
    if not rows:
        return set()
    if target_type == TARGET_DE:
        for row in rows:
            if row["slot_index"] == 0:
                return {row["last_two"]}
        return set()
    if target_type == TARGET_DAU:
        return {str(row["first_digit"]) for row in rows if row["first_digit"] is not None}
    if target_type == TARGET_DIT:
        return {str(row["last_digit"]) for row in rows if row["last_digit"] is not None}
    return {row["last_two"] for row in rows}
