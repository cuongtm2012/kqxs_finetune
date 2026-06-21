import logging
import time
from collections import defaultdict
from datetime import date, timedelta
from functools import lru_cache
from itertools import combinations
from typing import Literal, Optional

from app.db import fetch_all, fetch_one
from app.repositories.draw_repo import draw_repo

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "Thống kê dựa trên dữ liệu lịch sử XSMB. "
    "KQXS dựa trên quay số ngẫu nhiên. "
    "Không có mô hình thống kê nào beat random >1.15x liên tục. "
    "Thông tin mang tính tham khảo, không đảm bảo kết quả."
)

CANDIDATES_DISCLAIMER = (
    "Stats-based candidate pool. Lift-weighted score. Không phải dự đoán."
)

GAP_DISCLAIMER = (
    "Gap analysis dựa trên lịch sử. "
    "Không có cơ sở xác suất cho việc 'càng gan càng dễ về'."
)

WEEKDAYS_VI = (
    "Thứ hai",
    "Thứ ba",
    "Thứ tư",
    "Thứ năm",
    "Thứ sáu",
    "Thứ bảy",
    "Chủ nhật",
)

PairType = Literal["same-day", "lag-1"]
PairSort = Literal["lift", "count", "prob"]
HotColdSort = Literal["gap", "frequency", "pct_of_max"]
MaxCycleSort = Literal["pct_of_max", "gap", "max_gap"]
DigitType = Literal["dau", "dit", "both"]
CalendarBy = Literal["weekday", "dom", "month"]

DIGIT_BASELINE = 0.1
PAIR_BASELINE = 0.01

GAP_BUCKETS = [(0, 2), (3, 5), (6, 10), (11, 15), (16, 20), (21, 999)]

SAME_DAY_SQL = """
WITH daily AS (
  SELECT d.draw_date, p.last_two
  FROM draws d JOIN prizes p ON p.draw_id = d.id
  WHERE d.region = 'MB' AND d.draw_date BETWEEN %s AND %s
)
SELECT a.last_two AS x, b.last_two AS y, COUNT(*)::int AS co_occurrences
FROM daily a JOIN daily b
  ON a.draw_date = b.draw_date AND a.last_two < b.last_two
GROUP BY a.last_two, b.last_two
HAVING COUNT(*) >= %s
"""

LAG1_SQL = """
WITH daily AS (
  SELECT d.draw_date, ARRAY_AGG(DISTINCT p.last_two ORDER BY p.last_two) AS lotos
  FROM draws d JOIN prizes p ON p.draw_id = d.id
  WHERE d.region = 'MB' AND d.draw_date BETWEEN %s AND %s
  GROUP BY d.draw_date
)
SELECT y AS x, t AS y, COUNT(*)::int AS co_occurrences
FROM (
  SELECT LAG(lotos) OVER (ORDER BY draw_date) AS yesterday, lotos AS today
  FROM daily
) seq, unnest(seq.yesterday) AS y, unnest(seq.today) AS t
WHERE seq.yesterday IS NOT NULL
GROUP BY y, t
HAVING COUNT(*) >= %s
"""

LOTO_DAY_COUNTS_SQL = """
SELECT p.last_two AS loto, COUNT(DISTINCT d.draw_date)::int AS day_count
FROM draws d JOIN prizes p ON p.draw_id = d.id
WHERE d.region = 'MB' AND d.draw_date BETWEEN %s AND %s
GROUP BY p.last_two
"""

LAG1_SOURCE_COUNTS_SQL = """
WITH daily AS (
  SELECT d.draw_date, ARRAY_AGG(DISTINCT p.last_two ORDER BY p.last_two) AS lotos
  FROM draws d JOIN prizes p ON p.draw_id = d.id
  WHERE d.region = 'MB' AND d.draw_date BETWEEN %s AND %s
  GROUP BY d.draw_date
),
seq AS (
  SELECT LAG(lotos) OVER (ORDER BY draw_date) AS yesterday
  FROM daily
)
SELECT y AS loto, COUNT(*)::int AS source_days
FROM seq, unnest(seq.yesterday) AS y
WHERE seq.yesterday IS NOT NULL
GROUP BY y
"""


def _resolve_date_range(from_date: str, to_date: Optional[str]) -> tuple[str, str]:
    mb_range = draw_repo.mb_date_range() or {}
    resolved_to = to_date or mb_range.get("newest") or from_date
    return from_date, resolved_to


def _total_days(from_date: str, to_date: str) -> int:
    row = fetch_one(
        """
        SELECT COUNT(*)::int AS total
        FROM draws
        WHERE region = 'MB' AND draw_date BETWEEN %s AND %s
        """,
        (from_date, to_date),
    )
    return row["total"] if row else 0


def _round_prob(value: float) -> float:
    return round(value, 4)


def _round_lift(value: float) -> float:
    return round(value, 2)


def _sort_pairs(pairs: list[dict], sort: PairSort) -> list[dict]:
    key_map = {
        "lift": lambda r: (-r["lift"], -r["co_occurrences"]),
        "count": lambda r: (-r["co_occurrences"], -r["lift"]),
        "prob": lambda r: (-r["p_xy"], -r["lift"]),
    }
    return sorted(pairs, key=key_map[sort])


def _build_same_day_pairs(
    rows: list[dict],
    loto_days: dict[str, int],
    total_days: int,
    min_lift: float,
) -> tuple[list[dict], int]:
    pairs: list[dict] = []
    for row in rows:
        x, y = row["x"], row["y"]
        co_occ = row["co_occurrences"]
        p_x = loto_days.get(x, 0) / total_days
        p_y = loto_days.get(y, 0) / total_days
        p_xy = co_occ / total_days
        baseline = p_x * p_y
        lift = p_xy / baseline if baseline > 0 else 0.0
        pairs.append(
            {
                "x": x,
                "y": y,
                "co_occurrences": co_occ,
                "p_xy": _round_prob(p_xy),
                "p_x": _round_prob(p_x),
                "p_y": _round_prob(p_y),
                "baseline": _round_prob(baseline),
                "lift": _round_lift(lift),
                "significant": lift >= min_lift,
            }
        )
    random_expected = len(pairs)
    filtered = [p for p in pairs if p["significant"]]
    return filtered, random_expected


def _build_lag1_pairs(
    rows: list[dict],
    loto_days: dict[str, int],
    source_days: dict[str, int],
    total_days: int,
    min_lift: float,
) -> tuple[list[dict], int]:
    pairs: list[dict] = []
    for row in rows:
        x, y = row["x"], row["y"]
        co_occ = row["co_occurrences"]
        x_days = source_days.get(x, 0)
        p_xy = co_occ / x_days if x_days > 0 else 0.0
        p_y = loto_days.get(y, 0) / total_days
        baseline = p_y
        lift = p_xy / baseline if baseline > 0 else 0.0
        pairs.append(
            {
                "x": x,
                "y": y,
                "co_occurrences": co_occ,
                "p_xy": _round_prob(p_xy),
                "p_x": _round_prob(x_days / total_days) if total_days else 0.0,
                "p_y": _round_prob(p_y),
                "baseline": _round_prob(baseline),
                "lift": _round_lift(lift),
                "significant": lift >= min_lift,
            }
        )
    random_expected = len(pairs)
    filtered = [p for p in pairs if p["significant"]]
    return filtered, random_expected


def get_pairs(
    pair_type: PairType = "same-day",
    min_lift: float = 1.05,
    min_occ: int = 30,
    limit: int = 50,
    sort: PairSort = "lift",
    from_date: str = "2020-01-01",
    to_date: Optional[str] = None,
) -> dict:
    start_ms = time.perf_counter()
    from_date, to_date = _resolve_date_range(from_date, to_date)
    total_days = _total_days(from_date, to_date)

    if total_days == 0:
        return {
            "module": "pairs",
            "type": pair_type,
            "disclaimer": DISCLAIMER,
            "params": {
                "min_lift": min_lift,
                "min_occ": min_occ,
                "date_range": [from_date, to_date],
                "total_days": 0,
            },
            "data": [],
            "meta": {
                "query_time_ms": 0,
                "total_pairs": 0,
                "baseline_method": "P(X)*P(Y)" if pair_type == "same-day" else "P(Y)",
                "random_expected": 0,
            },
        }

    loto_rows = fetch_all(LOTO_DAY_COUNTS_SQL, (from_date, to_date))
    loto_days = {r["loto"]: r["day_count"] for r in loto_rows}

    if pair_type == "same-day":
        raw_rows = fetch_all(SAME_DAY_SQL, (from_date, to_date, min_occ))
        pairs, random_expected = _build_same_day_pairs(raw_rows, loto_days, total_days, min_lift)
        baseline_method = "P(X)*P(Y)"
    else:
        raw_rows = fetch_all(LAG1_SQL, (from_date, to_date, min_occ))
        source_rows = fetch_all(LAG1_SOURCE_COUNTS_SQL, (from_date, to_date))
        source_days = {r["loto"]: r["source_days"] for r in source_rows}
        pairs, random_expected = _build_lag1_pairs(
            raw_rows, loto_days, source_days, total_days, min_lift
        )
        baseline_method = "P(Y)"

    pairs = _sort_pairs(pairs, sort)[:limit]
    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)

    return {
        "module": "pairs",
        "type": pair_type,
        "disclaimer": DISCLAIMER,
        "params": {
            "min_lift": min_lift,
            "min_occ": min_occ,
            "date_range": [from_date, to_date],
            "total_days": total_days,
        },
        "data": pairs,
        "meta": {
            "query_time_ms": elapsed_ms,
            "total_pairs": len(pairs),
            "baseline_method": baseline_method,
            "random_expected": random_expected,
        },
    }


def _vietnamese_weekday(draw_date: str) -> str:
    d = date.fromisoformat(draw_date)
    return WEEKDAYS_VI[d.weekday()]


def _draw_dates(window: int = 0) -> list[str]:
    rows = fetch_all(
        "SELECT draw_date::text AS d FROM draws WHERE region = 'MB' ORDER BY draw_date"
    )
    dates = [r["d"] for r in rows]
    if window > 0:
        dates = dates[-window:]
    return dates


def _date_index(dates: list[str]) -> dict[str, int]:
    return {d: i for i, d in enumerate(dates)}


def _loto_hit_indices(hit_dates: list[str], date_to_idx: dict[str, int]) -> list[int]:
    return [date_to_idx[d] for d in hit_dates if d in date_to_idx]


def _gaps_between_hits(indices: list[int]) -> list[int]:
    if len(indices) < 2:
        return []
    return [indices[i + 1] - indices[i] for i in range(len(indices) - 1)]


def _current_gap(indices: list[int], latest_idx: int) -> int:
    if not indices:
        return latest_idx + 1
    return latest_idx - indices[-1]


def _gap_distribution(gaps: list[int]) -> list[dict]:
    buckets = {f"{lo}-{hi}": 0 for lo, hi in GAP_BUCKETS}
    for gap in gaps:
        for lo, hi in GAP_BUCKETS:
            if lo <= gap <= hi:
                buckets[f"{lo}-{hi}"] += 1
                break
    return [{"range": k, "count": v} for k, v in buckets.items() if v > 0 or k == "0-2"]


def _max_cycle(indices: list[int], draw_dates: list[str]) -> dict:
    gaps = _gaps_between_hits(indices)
    if not gaps:
        return {"value": 0, "from_date": None, "to_date": None}
    max_gap = max(gaps)
    for i, gap in enumerate(gaps):
        if gap == max_gap:
            return {
                "value": max_gap,
                "from_date": draw_dates[indices[i]],
                "to_date": draw_dates[indices[i + 1]],
            }
    return {"value": 0, "from_date": None, "to_date": None}


def _median(values: list[int]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2


def _loto_summary(
    hit_dates: list[str],
    draw_dates: list[str],
    date_to_idx: dict[str, int],
) -> dict:
    indices = _loto_hit_indices(hit_dates, date_to_idx)
    latest_idx = len(draw_dates) - 1
    gaps = _gaps_between_hits(indices)
    cur_gap = _current_gap(indices, latest_idx)
    max_gap_hist = max(gaps) if gaps else cur_gap
    pct_of_max = round(cur_gap / max_gap_hist * 100) if max_gap_hist > 0 else 0
    total_days = len(draw_dates)
    frequency = round(len(indices) / total_days, 4) if total_days else 0.0
    last_seen = hit_dates[-1] if hit_dates else None
    return {
        "current_gap": cur_gap,
        "last_seen": last_seen,
        "max_gap_hist": max_gap_hist,
        "pct_of_max": pct_of_max,
        "frequency": frequency,
        "total_occurrences": len(indices),
        "gaps": gaps,
        "indices": indices,
    }


def clear_stats_cache() -> None:
    _cached_all_loto_hits.cache_clear()
    _cached_de_slot_days.cache_clear()


@lru_cache(maxsize=1)
def _cached_all_loto_hits() -> dict[str, list[str]]:
    rows = fetch_all(
        """
        SELECT p.last_two AS loto, d.draw_date::text AS draw_date
        FROM draws d JOIN prizes p ON p.draw_id = d.id
        WHERE d.region = 'MB'
        ORDER BY loto, draw_date
        """
    )
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        grouped[row["loto"]].append(row["draw_date"])
    return dict(grouped)


def _all_loto_hits() -> dict[str, list[str]]:
    return _cached_all_loto_hits()


def get_gap_detail(loto: str, window: int = 0) -> dict:
    start_ms = time.perf_counter()
    draw_dates = _draw_dates(window)
    date_to_idx = _date_index(draw_dates)

    rows = fetch_all(
        """
        SELECT d.draw_date::text AS draw_date,
               ARRAY_AGG(DISTINCT p.prize_level ORDER BY p.prize_level) AS prizes
        FROM draws d JOIN prizes p ON p.draw_id = d.id
        WHERE d.region = 'MB' AND p.last_two = %s
        GROUP BY d.draw_date
        ORDER BY d.draw_date
        """,
        (loto,),
    )
    all_hit_dates = [r["draw_date"] for r in rows]
    if window > 0 and draw_dates:
        first = draw_dates[0]
        hit_dates = [d for d in all_hit_dates if d >= first]
    else:
        hit_dates = all_hit_dates

    summary = _loto_summary(hit_dates, draw_dates, date_to_idx)
    gaps = summary["gaps"]
    cur_gap = summary["current_gap"]
    times_exceeded = sum(1 for g in gaps if g > cur_gap)

    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
    return {
        "module": "gap",
        "type": "detail",
        "loto": loto,
        "disclaimer": DISCLAIMER,
        "current_gap": cur_gap,
        "last_seen": summary["last_seen"],
        "history": {
            "max_gap": summary["max_gap_hist"],
            "min_gap": min(gaps) if gaps else 0,
            "avg_gap": round(sum(gaps) / len(gaps), 1) if gaps else 0.0,
            "median_gap": _median(gaps),
            "max_cycle": _max_cycle(summary["indices"], draw_dates),
            "gap_distribution": _gap_distribution(gaps),
            "total_occurrences": summary["total_occurrences"],
            "times_exceeded_current_gap": times_exceeded,
        },
        "meta": {
            "total_days": len(draw_dates),
            "query_time_ms": elapsed_ms,
            "gap_disclaimer": GAP_DISCLAIMER,
        },
    }


def get_gap_hot_cold(
    sort: HotColdSort = "gap",
    limit: int = 30,
    min_gap: int = 5,
) -> dict:
    start_ms = time.perf_counter()
    draw_dates = _draw_dates()
    date_to_idx = _date_index(draw_dates)
    loto_hits = _all_loto_hits()

    rows: list[dict] = []
    for loto, hit_dates in loto_hits.items():
        summary = _loto_summary(hit_dates, draw_dates, date_to_idx)
        if summary["current_gap"] < min_gap:
            continue
        rows.append(
            {
                "loto": loto,
                "current_gap": summary["current_gap"],
                "last_seen": summary["last_seen"],
                "frequency": summary["frequency"],
                "max_gap_hist": summary["max_gap_hist"],
                "pct_of_max": summary["pct_of_max"],
            }
        )

    sort_keys = {
        "gap": lambda r: (-r["current_gap"], -r["pct_of_max"]),
        "frequency": lambda r: (-r["frequency"], -r["current_gap"]),
        "pct_of_max": lambda r: (-r["pct_of_max"], -r["current_gap"]),
    }
    rows = sorted(rows, key=sort_keys[sort])[:limit]
    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)

    return {
        "module": "gap",
        "type": "hot-cold",
        "disclaimer": DISCLAIMER,
        "params": {"sort": sort, "limit": limit, "min_gap": min_gap},
        "data": rows,
        "meta": {
            "total_days": len(draw_dates),
            "query_time_ms": elapsed_ms,
            "gap_disclaimer": GAP_DISCLAIMER,
        },
    }


def get_gap_nhip(
    loto: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> dict:
    start_ms = time.perf_counter()
    mb_range = draw_repo.mb_date_range() or {}
    resolved_to = to_date or mb_range.get("newest") or date.today().isoformat()
    if from_date:
        resolved_from = from_date
    else:
        resolved_from = (date.fromisoformat(resolved_to) - timedelta(days=30)).isoformat()
    resolved_from, resolved_to = _resolve_date_range(resolved_from, resolved_to)

    draw_dates = _draw_dates()
    date_to_idx = _date_index(draw_dates)

    range_rows = fetch_all(
        """
        SELECT d.draw_date::text AS draw_date,
               ARRAY_AGG(DISTINCT p.prize_level ORDER BY p.prize_level) AS prizes,
               COUNT(*)::int AS hit_count
        FROM draws d JOIN prizes p ON p.draw_id = d.id
        WHERE d.region = 'MB' AND p.last_two = %s
          AND d.draw_date BETWEEN %s AND %s
        GROUP BY d.draw_date
        ORDER BY d.draw_date
        """,
        (loto, resolved_from, resolved_to),
    )

    prior_hit = fetch_one(
        """
        SELECT d.draw_date::text AS draw_date
        FROM draws d JOIN prizes p ON p.draw_id = d.id
        WHERE d.region = 'MB' AND p.last_two = %s AND d.draw_date < %s
        ORDER BY d.draw_date DESC
        LIMIT 1
        """,
        (loto, resolved_from),
    )
    prev_idx = date_to_idx.get(prior_hit["draw_date"]) if prior_hit else None

    data: list[dict] = []
    nhips: list[int] = []
    for row in range_rows:
        draw_date = row["draw_date"]
        idx = date_to_idx.get(draw_date)
        nhip = idx - prev_idx if prev_idx is not None and idx is not None else 0
        if prev_idx is not None and idx is not None:
            nhips.append(nhip)
        if idx is not None:
            prev_idx = idx
        data.append(
            {
                "date": draw_date,
                "weekday": _vietnamese_weekday(draw_date),
                "count": row["hit_count"],
                "prizes": row["prizes"],
                "nhip": nhip,
            }
        )

    data.reverse()
    avg_nhip = round(sum(nhips) / len(nhips), 1) if nhips else 0.0
    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)

    return {
        "module": "gap",
        "type": "nhip",
        "loto": loto,
        "disclaimer": DISCLAIMER,
        "from_date": resolved_from,
        "to_date": resolved_to,
        "data": data,
        "total_occurrences": len(data),
        "avg_nhip": avg_nhip,
        "meta": {"query_time_ms": elapsed_ms, "gap_disclaimer": GAP_DISCLAIMER},
    }


def get_gap_max_cycle(
    limit: int = 30,
    min_gap: int = 5,
    sort: MaxCycleSort = "pct_of_max",
) -> dict:
    start_ms = time.perf_counter()
    draw_dates = _draw_dates()
    date_to_idx = _date_index(draw_dates)
    loto_hits = _all_loto_hits()

    rows: list[dict] = []
    for loto, hit_dates in loto_hits.items():
        summary = _loto_summary(hit_dates, draw_dates, date_to_idx)
        if summary["current_gap"] < min_gap:
            continue
        rows.append(
            {
                "loto": loto,
                "current_gap": summary["current_gap"],
                "max_gap_hist": summary["max_gap_hist"],
                "pct_of_max": summary["pct_of_max"],
                "frequency": summary["frequency"],
                "last_seen": summary["last_seen"],
            }
        )

    sort_keys = {
        "pct_of_max": lambda r: (-r["pct_of_max"], -r["current_gap"]),
        "gap": lambda r: (-r["current_gap"], -r["pct_of_max"]),
        "max_gap": lambda r: (-r["max_gap_hist"], -r["pct_of_max"]),
    }
    rows = sorted(rows, key=sort_keys[sort])[:limit]
    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)

    return {
        "module": "gap",
        "type": "max-cycle",
        "disclaimer": DISCLAIMER,
        "params": {"limit": limit, "min_gap": min_gap, "sort": sort},
        "data": rows,
        "meta": {
            "total_days": len(draw_dates),
            "query_time_ms": elapsed_ms,
            "gap_disclaimer": GAP_DISCLAIMER,
        },
    }


def _draw_date_filter_sql(window: int) -> tuple[str, tuple]:
    if window <= 0:
        return "", ()
    return (
        """
        AND d.draw_date >= (
          SELECT draw_date FROM draws WHERE region = 'MB'
          ORDER BY draw_date DESC OFFSET %s LIMIT 1
        )
        """,
        (window - 1,),
    )


def _load_mb_days(window: int = 0) -> list[dict]:
    clause, params = _draw_date_filter_sql(window)
    rows = fetch_all(
        f"""
        SELECT d.draw_date::text AS draw_date, p.slot_index, p.last_two,
               p.number, p.first_digit::text AS first_digit, p.last_digit::text AS last_digit
        FROM draws d JOIN prizes p ON p.draw_id = d.id
        WHERE d.region = 'MB' {clause}
        ORDER BY d.draw_date, p.slot_index
        """,
        params,
    )
    by_date: dict[str, dict] = {}
    for row in rows:
        draw_date = row["draw_date"]
        if draw_date not in by_date:
            by_date[draw_date] = {
                "draw_date": draw_date,
                "de": "",
                "de_number": "",
                "de_dau": "",
                "loto_set": set(),
                "dau_digits": [],
                "dit_digits": [],
            }
        rec = by_date[draw_date]
        loto = row["last_two"]
        rec["loto_set"].add(loto)
        if row["first_digit"] is not None:
            rec["dau_digits"].append(row["first_digit"])
        if row["last_digit"] is not None:
            rec["dit_digits"].append(row["last_digit"])
        if row["slot_index"] == 0:
            rec["de"] = loto
            rec["de_number"] = row["number"] or loto
            rec["de_dau"] = row["first_digit"] or (loto[0] if loto else "")
            rec["de_dit"] = row["last_digit"] or (loto[1] if len(loto) >= 2 else "")
    return [by_date[k] for k in sorted(by_date.keys())]


def _digit_distribution(counts: dict[str, int], total: int) -> list[dict]:
    rows = []
    for digit in range(10):
        d = str(digit)
        count = counts.get(d, 0)
        prob = count / total if total else 0.0
        rows.append(
            {
                "digit": d,
                "count": count,
                "prob": _round_prob(prob),
                "baseline": DIGIT_BASELINE,
                "lift": _round_lift(prob / DIGIT_BASELINE) if DIGIT_BASELINE else 0.0,
            }
        )
    return rows


def get_digits(digit_type: DigitType = "both", window: int = 0) -> dict:
    start_ms = time.perf_counter()
    clause, params = _draw_date_filter_sql(window)
    dau_rows = fetch_all(
        f"""
        SELECT p.first_digit::text AS digit, COUNT(*)::int AS count
        FROM prizes p JOIN draws d ON d.id = p.draw_id
        WHERE d.region = 'MB' AND p.first_digit IS NOT NULL {clause}
        GROUP BY p.first_digit
        """,
        params,
    )
    dit_rows = fetch_all(
        f"""
        SELECT p.last_digit::text AS digit, COUNT(*)::int AS count
        FROM prizes p JOIN draws d ON d.id = p.draw_id
        WHERE d.region = 'MB' AND p.last_digit IS NOT NULL {clause}
        GROUP BY p.last_digit
        """,
        params,
    )
    pair_rows = fetch_all(
        f"""
        SELECT p.first_digit::text AS dau, p.last_digit::text AS dit, COUNT(*)::int AS count
        FROM prizes p JOIN draws d ON d.id = p.draw_id
        WHERE d.region = 'MB'
          AND p.first_digit IS NOT NULL AND p.last_digit IS NOT NULL {clause}
        GROUP BY p.first_digit, p.last_digit
        ORDER BY count DESC
        """,
        params,
    )

    dau_counts = {r["digit"]: r["count"] for r in dau_rows}
    dit_counts = {r["digit"]: r["count"] for r in dit_rows}
    dau_total = sum(dau_counts.values())
    dit_total = sum(dit_counts.values())
    pair_total = sum(r["count"] for r in pair_rows)

    pairs = []
    for row in pair_rows:
        prob = row["count"] / pair_total if pair_total else 0.0
        pairs.append(
            {
                "dau": row["dau"],
                "dit": row["dit"],
                "count": row["count"],
                "prob": _round_prob(prob),
                "baseline": PAIR_BASELINE,
                "lift": _round_lift(prob / PAIR_BASELINE) if PAIR_BASELINE else 0.0,
            }
        )

    data: dict = {}
    if digit_type in ("dau", "both"):
        data["dau"] = _digit_distribution(dau_counts, dau_total)
    if digit_type in ("dit", "both"):
        data["dit"] = _digit_distribution(dit_counts, dit_total)

    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
    return {
        "module": "digits",
        "type": digit_type,
        "disclaimer": DISCLAIMER,
        "params": {"type": digit_type, "window": window},
        "data": data,
        "pairs": pairs if digit_type == "both" else [],
        "meta": {
            "dau_total": dau_total,
            "dit_total": dit_total,
            "pair_total": pair_total,
            "query_time_ms": elapsed_ms,
        },
    }


def get_de_dau() -> dict:
    start_ms = time.perf_counter()
    rows = fetch_all(
        """
        SELECT d.draw_date::text AS draw_date, p.number, p.last_two, p.first_digit::text AS de_dau
        FROM draws d JOIN prizes p ON p.draw_id = d.id
        WHERE d.region = 'MB' AND p.slot_index = 0
        ORDER BY d.draw_date
        """
    )
    draw_dates = [r["draw_date"] for r in rows]
    date_to_idx = _date_index(draw_dates)

    digit_hits: dict[str, list[str]] = {str(i): [] for i in range(10)}
    de_last_map: dict[str, str] = {}
    for row in rows:
        digit = row["de_dau"] or (row["last_two"][0] if row["last_two"] else None)
        if digit is None:
            continue
        digit_hits[digit].append(row["draw_date"])
        de_last_map[digit] = row["number"] or row["last_two"]

    latest_idx = len(draw_dates) - 1
    data = []
    for digit in range(10):
        d = str(digit)
        hit_dates = digit_hits[d]
        indices = _loto_hit_indices(hit_dates, date_to_idx)
        gaps = _gaps_between_hits(indices)
        cur_gap = _current_gap(indices, latest_idx)
        data.append(
            {
                "digit": d,
                "current_gap": cur_gap,
                "last_seen": hit_dates[-1] if hit_dates else None,
                "max_gap_hist": max(gaps) if gaps else cur_gap,
                "de_last": de_last_map.get(d),
            }
        )

    data.sort(key=lambda r: -r["current_gap"])
    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
    return {
        "module": "digits",
        "type": "de-dau",
        "disclaimer": DISCLAIMER,
        "data": data,
        "meta": {"total_days": len(draw_dates), "query_time_ms": elapsed_ms},
    }


def get_lo_roi(
    loto: Optional[str] = None,
    de: Optional[str] = None,
    window: int = 3,
    limit: int = 20,
) -> dict:
    start_ms = time.perf_counter()
    days = _load_mb_days()
    total_days = len(days)

    loto_day_counts: dict[str, int] = defaultdict(int)
    for day in days:
        for lot in day["loto_set"]:
            loto_day_counts[lot] += 1

    stats: dict[tuple[str, str], dict] = defaultdict(lambda: {"occurrences": 0, "falls": 0})
    target_lotos = [loto] if loto else sorted(loto_day_counts.keys())

    if len(days) > window:
        window_lotos: set[str] = set()
        for j in range(1, window + 1):
            window_lotos |= days[j]["loto_set"]

        for i in range(len(days) - window):
            de_val = days[i]["de"]
            if de_val and (not de or de_val == de):
                for lot in target_lotos:
                    stats[(de_val, lot)]["occurrences"] += 1
                    if lot in window_lotos:
                        stats[(de_val, lot)]["falls"] += 1

            if i + window + 1 < len(days):
                window_lotos -= days[i + 1]["loto_set"]
                window_lotos |= days[i + window + 1]["loto_set"]

    rows: list[dict] = []
    for (de_val, lot_val), agg in stats.items():
        occ = agg["occurrences"]
        if occ == 0:
            continue
        falls = agg["falls"]
        prob = falls / occ
        baseline = loto_day_counts[lot_val] / total_days if total_days else 0.0
        lift = prob / baseline if baseline > 0 else 0.0
        rows.append(
            {
                "loto": lot_val,
                "de": de_val,
                "occurrences": occ,
                "falls": falls,
                "prob": _round_prob(prob),
                "baseline": _round_prob(baseline),
                "lift": _round_lift(lift),
            }
        )

    rows.sort(key=lambda r: (-r["lift"], -r["prob"], -r["occurrences"]))
    rows = rows[:limit]
    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)

    return {
        "module": "lo-roi",
        "disclaimer": DISCLAIMER,
        "params": {"loto": loto, "de": de, "window": window, "limit": limit},
        "data": rows,
        "meta": {
            "total_days": total_days,
            "query_time_ms": elapsed_ms,
            "baseline_method": "P(loto về trong ngày)",
        },
    }


def _bucket_id(draw_date: str, by: CalendarBy) -> int:
    d = date.fromisoformat(draw_date)
    if by == "weekday":
        return d.weekday()
    if by == "dom":
        return d.day
    return d.month


def _bucket_label(by: CalendarBy, bucket_id: int) -> str:
    if by == "weekday":
        return WEEKDAYS_VI[bucket_id]
    if by == "dom":
        return str(bucket_id)
    return f"Tháng {bucket_id}"


def _calendar_stats(
    days: list[dict],
    by: CalendarBy,
    loto: Optional[str] = None,
) -> tuple[dict[int, int], dict[str, dict[int, int]], dict[str, int]]:
    bucket_days: dict[int, int] = defaultdict(int)
    loto_bucket_hits: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    loto_total_hits: dict[str, int] = defaultdict(int)

    for day in days:
        bucket = _bucket_id(day["draw_date"], by)
        bucket_days[bucket] += 1
        for lot in day["loto_set"]:
            loto_bucket_hits[lot][bucket] += 1
            loto_total_hits[lot] += 1

    if loto:
        loto_bucket_hits = {loto: loto_bucket_hits.get(loto, defaultdict(int))}
        loto_total_hits = {loto: loto_total_hits.get(loto, 0)}

    return bucket_days, loto_bucket_hits, loto_total_hits


def _calendar_rows(
    days: list[dict],
    by: CalendarBy,
    loto: Optional[str] = None,
    top_per_bucket: int = 10,
) -> list[dict]:
    total_days = len(days)
    bucket_days, loto_bucket_hits, loto_total_hits = _calendar_stats(days, by, loto)
    rows: list[dict] = []

    if loto:
        for bucket, opportunities in sorted(bucket_days.items()):
            hits = loto_bucket_hits[loto].get(bucket, 0)
            prob = hits / opportunities if opportunities else 0.0
            baseline = loto_total_hits[loto] / total_days if total_days else 0.0
            lift = prob / baseline if baseline > 0 else 0.0
            rows.append(
                {
                    "bucket": _bucket_label(by, bucket),
                    "bucket_id": bucket,
                    "loto": loto,
                    "hits": hits,
                    "opportunities": opportunities,
                    "prob": _round_prob(prob),
                    "baseline": _round_prob(baseline),
                    "lift": _round_lift(lift),
                }
            )
        return rows

    for bucket, opportunities in sorted(bucket_days.items()):
        bucket_rows = []
        for lot, bucket_hits in loto_bucket_hits.items():
            hits = bucket_hits.get(bucket, 0)
            if hits == 0:
                continue
            prob = hits / opportunities if opportunities else 0.0
            baseline = loto_total_hits[lot] / total_days if total_days else 0.0
            lift = prob / baseline if baseline > 0 else 0.0
            bucket_rows.append(
                {
                    "loto": lot,
                    "hits": hits,
                    "opportunities": opportunities,
                    "prob": _round_prob(prob),
                    "baseline": _round_prob(baseline),
                    "lift": _round_lift(lift),
                }
            )
        bucket_rows.sort(key=lambda r: (-r["lift"], -r["prob"]))
        rows.append(
            {
                "bucket": _bucket_label(by, bucket),
                "bucket_id": bucket,
                "top": bucket_rows[:top_per_bucket],
            }
        )
    return rows


def calendar_bias_matches(
    weekday: int,
    min_lift: float = 1.05,
    window: int = 0,
) -> dict[str, dict]:
    days = _load_mb_days(window)
    bucket_days, loto_bucket_hits, loto_total_hits = _calendar_stats(days, "weekday")
    opportunities = bucket_days.get(weekday, 0)
    total_days = len(days)
    matches: dict[str, dict] = {}
    if opportunities == 0:
        return matches

    for lot, bucket_hits in loto_bucket_hits.items():
        hits = bucket_hits.get(weekday, 0)
        prob = hits / opportunities
        baseline = loto_total_hits[lot] / total_days if total_days else 0.0
        lift = prob / baseline if baseline > 0 else 0.0
        if lift >= min_lift:
            matches[lot] = {
                "hits": hits,
                "opportunities": opportunities,
                "prob": _round_prob(prob),
                "baseline": _round_prob(baseline),
                "lift": _round_lift(lift),
                "weekday": WEEKDAYS_VI[weekday],
            }
    return matches


def get_calendar(
    by: CalendarBy = "weekday",
    loto: Optional[str] = None,
    window: int = 0,
) -> dict:
    start_ms = time.perf_counter()
    days = _load_mb_days(window)
    data = _calendar_rows(days, by, loto=loto)
    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
    return {
        "module": "calendar",
        "by": by,
        "disclaimer": DISCLAIMER,
        "params": {"by": by, "loto": loto, "window": window},
        "data": data,
        "meta": {"total_days": len(days), "query_time_ms": elapsed_ms},
    }


def get_loto_theo_db(
    de: Optional[str] = None,
    limit: int = 20,
    window: int = 0,
) -> dict:
    start_ms = time.perf_counter()
    days = _load_mb_days(window)
    stats: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    totals: dict[str, int] = defaultdict(int)

    for i in range(len(days) - 1):
        de_val = days[i]["de"]
        if not de_val:
            continue
        if de and de_val != de:
            continue
        totals[de_val] += 1
        for lot in days[i + 1]["loto_set"]:
            stats[de_val][lot] += 1

    rows: list[dict] = []
    for de_val, loto_counts in stats.items():
        total = totals[de_val]
        for lot, count in loto_counts.items():
            prob = count / total if total else 0.0
            rows.append(
                {
                    "de": de_val,
                    "loto": lot,
                    "occurrences": count,
                    "de_days": total,
                    "prob": _round_prob(prob),
                }
            )

    rows.sort(key=lambda r: (-r["prob"], -r["occurrences"]))
    rows = rows[:limit]
    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
    return {
        "module": "calendar",
        "type": "loto-theo-db",
        "disclaimer": DISCLAIMER,
        "params": {"de": de, "limit": limit, "window": window},
        "data": rows,
        "meta": {"query_time_ms": elapsed_ms, "total_days": len(days)},
    }


def get_loto_theo_loto(
    loto: Optional[str] = None,
    limit: int = 20,
    window: int = 0,
) -> dict:
    start_ms = time.perf_counter()
    days = _load_mb_days(window)
    stats: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    totals: dict[str, int] = defaultdict(int)

    for i in range(len(days) - 1):
        sources = [loto] if loto else list(days[i]["loto_set"])
        if loto and loto not in days[i]["loto_set"]:
            continue
        for src in sources:
            if loto and src != loto:
                continue
            totals[src] += 1
            for target in days[i + 1]["loto_set"]:
                stats[src][target] += 1

    rows: list[dict] = []
    for src, loto_counts in stats.items():
        total = totals[src]
        for target, count in loto_counts.items():
            prob = count / total if total else 0.0
            rows.append(
                {
                    "from_loto": src,
                    "to_loto": target,
                    "occurrences": count,
                    "source_days": total,
                    "prob": _round_prob(prob),
                }
            )

    rows.sort(key=lambda r: (-r["prob"], -r["occurrences"]))
    rows = rows[:limit]
    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
    return {
        "module": "calendar",
        "type": "loto-theo-loto",
        "disclaimer": DISCLAIMER,
        "params": {"loto": loto, "limit": limit, "window": window},
        "data": rows,
        "meta": {"query_time_ms": elapsed_ms, "total_days": len(days)},
    }


@lru_cache(maxsize=1)
def _cached_de_slot_days() -> list[dict]:
    rows = fetch_all(
        """
        SELECT d.draw_date::text AS draw_date, p.last_two AS de,
               p.first_digit::text AS de_dau, p.last_digit::text AS de_dit
        FROM draws d JOIN prizes p ON p.draw_id = d.id
        WHERE d.region = 'MB' AND p.slot_index = 0
        ORDER BY d.draw_date
        """
    )
    result: list[dict] = []
    for row in rows:
        de = row["de"] or ""
        de_dau = row["de_dau"] or (de[0] if de else "")
        de_dit = row["de_dit"] or (de[1] if len(de) >= 2 else "")
        result.append(
            {
                "draw_date": row["draw_date"],
                "de": de,
                "de_dau": de_dau,
                "de_dit": de_dit,
            }
        )
    return result


def de_lag1_matches(yesterday_de: str, min_lift: float = 1.05) -> dict[str, dict]:
    if not yesterday_de:
        return {}
    days = _cached_de_slot_days()
    transitions: dict[str, int] = defaultdict(int)
    total_from = 0
    de_totals: dict[str, int] = defaultdict(int)
    total_days = len(days)
    for day in days:
        de_totals[day["de"]] += 1
    for i in range(len(days) - 1):
        if days[i]["de"] == yesterday_de:
            total_from += 1
            transitions[days[i + 1]["de"]] += 1
    if total_from == 0:
        return {}

    matches: dict[str, dict] = {}
    for de_val, count in transitions.items():
        p_xy = count / total_from
        baseline = de_totals[de_val] / total_days if total_days else 0.0
        lift = p_xy / baseline if baseline > 0 else 0.0
        if lift >= min_lift:
            matches[de_val] = {
                "from_de": yesterday_de,
                "de": de_val,
                "occurrences": count,
                "total_from": total_from,
                "p_xy": _round_prob(p_xy),
                "baseline": _round_prob(baseline),
                "lift": _round_lift(lift),
            }
    return matches


def de_calendar_matches(weekday: int, min_lift: float = 1.05) -> dict[str, dict]:
    days = _cached_de_slot_days()
    bucket_days = sum(
        1 for day in days if date.fromisoformat(day["draw_date"]).weekday() == weekday
    )
    if bucket_days == 0:
        return {}

    de_bucket: dict[str, int] = defaultdict(int)
    de_total: dict[str, int] = defaultdict(int)
    total_days = len(days)
    for day in days:
        de_val = day["de"]
        if not de_val:
            continue
        de_total[de_val] += 1
        if date.fromisoformat(day["draw_date"]).weekday() == weekday:
            de_bucket[de_val] += 1

    matches: dict[str, dict] = {}
    for de_val, hits in de_bucket.items():
        prob = hits / bucket_days
        baseline = de_total[de_val] / total_days if total_days else 0.0
        lift = prob / baseline if baseline > 0 else 0.0
        if lift >= min_lift:
            matches[de_val] = {
                "hits": hits,
                "opportunities": bucket_days,
                "prob": _round_prob(prob),
                "baseline": _round_prob(baseline),
                "lift": _round_lift(lift),
                "weekday": WEEKDAYS_VI[weekday],
            }
    return matches


def de_max_cycle_matches(min_pct: int = 70) -> dict[str, dict]:
    days = _cached_de_slot_days()
    draw_dates = [day["draw_date"] for day in days]
    date_to_idx = _date_index(draw_dates)
    de_hit_dates: dict[str, list[str]] = defaultdict(list)
    for day in days:
        de_hit_dates[day["de"]].append(day["draw_date"])

    matches: dict[str, dict] = {}
    for de_val, hit_dates in de_hit_dates.items():
        summary = _loto_summary(hit_dates, draw_dates, date_to_idx)
        if summary["pct_of_max"] >= min_pct:
            matches[de_val] = summary
    return matches


def de_loto_boost_matches(yesterday_lotos: set[str], min_lift: float = 1.05) -> dict[str, dict]:
    if not yesterday_lotos:
        return {}
    days = _load_mb_days()
    total_days = len(days)
    de_totals: dict[str, int] = defaultdict(int)
    for day in days:
        de_totals[day["de"]] += 1

    matches: dict[str, dict] = {}
    for lot in yesterday_lotos:
        occ = 0
        hits = 0
        for i in range(len(days) - 1):
            if lot in days[i]["loto_set"]:
                occ += 1
                if days[i + 1]["de"] == lot:
                    hits += 1
        if occ < 10:
            continue
        p_cond = hits / occ
        baseline = de_totals[lot] / total_days if total_days else 0.0
        lift = p_cond / baseline if baseline > 0 else 0.0
        if lift >= min_lift:
            matches[lot] = {
                "loto": lot,
                "occurrences": hits,
                "loto_days": occ,
                "prob": _round_prob(p_cond),
                "baseline": _round_prob(baseline),
                "lift": _round_lift(lift),
            }
    return matches


CondFreqSort = Literal["count", "lift"]


def get_conditional_frequency(
    db_loto: str,
    target_weekday: Optional[int] = None,
    min_occ: int = 2,
    limit: int = 30,
    sort: CondFreqSort = "count",
    history_limit: int = 20,
) -> dict:
    """target_weekday uses Python convention (Mon=0 .. Sun=6); API converts SPEC weekday."""
    start_ms = time.perf_counter()
    rows = fetch_all(
        """
        SELECT d.draw_date::text AS draw_date, p.last_two, p.number
        FROM draws d JOIN prizes p ON p.draw_id = d.id
        WHERE d.region = 'MB' AND p.prize_level = 'DB'
        ORDER BY d.draw_date
        """
    )
    pairs: list[dict] = []
    for i in range(len(rows) - 1):
        cur = rows[i]
        nxt = rows[i + 1]
        if cur["last_two"] != db_loto:
            continue
        next_dt = date.fromisoformat(nxt["draw_date"])
        if target_weekday is not None and next_dt.weekday() != target_weekday:
            continue
        pairs.append(
            {
                "date": cur["draw_date"],
                "db": cur["number"] or cur["last_two"],
                "next_date": nxt["draw_date"],
                "next_db": nxt["number"] or nxt["last_two"],
                "next_loto": nxt["last_two"],
            }
        )

    total_samples = len(pairs)
    loto_counts: dict[str, int] = defaultdict(int)
    dau_counts: dict[str, int] = defaultdict(int)
    duoi_counts: dict[str, int] = defaultdict(int)
    tong_counts: dict[str, int] = defaultdict(int)

    for pair in pairs:
        lot = pair["next_loto"]
        loto_counts[lot] += 1
        if len(lot) >= 2:
            dau = lot[0]
            duoi = lot[1]
            tong = str((int(lot[0]) + int(lot[1])) % 10)
            dau_counts[dau] += 1
            duoi_counts[duoi] += 1
            tong_counts[tong] += 1

    loto_frequency: list[dict] = []
    baseline_pct = 1.0
    for lot, count in loto_counts.items():
        if count < min_occ:
            continue
        pct = count / total_samples * 100 if total_samples else 0.0
        lift = pct / baseline_pct if baseline_pct > 0 else 0.0
        loto_frequency.append(
            {
                "loto": lot,
                "count": count,
                "pct": round(pct, 1),
                "baseline": baseline_pct,
                "lift": _round_lift(lift),
            }
        )

    if sort == "lift":
        loto_frequency.sort(key=lambda r: (-r["lift"], -r["count"]))
    else:
        loto_frequency.sort(key=lambda r: (-r["count"], -r["lift"]))
    loto_frequency = loto_frequency[:limit]

    def _digit_stats(counts: dict[str, int]) -> list[dict]:
        if total_samples == 0:
            return []
        stats = []
        for digit in range(10):
            d = str(digit)
            c = counts.get(d, 0)
            if c == 0:
                continue
            stats.append(
                {
                    "digit": d,
                    "count": c,
                    "pct": round(c / total_samples * 100, 1),
                }
            )
        stats.sort(key=lambda r: -r["count"])
        return stats

    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
    return {
        "module": "conditional-frequency",
        "db_loto": db_loto,
        "target_weekday": target_weekday,
        "total_samples": total_samples,
        "params": {
            "db_loto": db_loto,
            "target_weekday": target_weekday,
            "min_occ": min_occ,
            "limit": limit,
            "sort": sort,
        },
        "loto_frequency": loto_frequency,
        "cham_stats": {
            "dau": _digit_stats(dau_counts),
            "duoi": _digit_stats(duoi_counts),
            "tong": _digit_stats(tong_counts),
        },
        "history": pairs[-history_limit:],
        "meta": {"query_time_ms": elapsed_ms},
    }


def conditional_frequency_matches(
    db_loto: str,
    target_weekday: Optional[int] = None,
    min_occ: int = 2,
    min_lift: float = 1.05,
) -> dict[str, dict]:
    if not db_loto:
        return {}
    result = get_conditional_frequency(
        db_loto=db_loto,
        target_weekday=target_weekday,
        min_occ=min_occ,
        limit=100,
        sort="lift",
    )
    matches: dict[str, dict] = {}
    for row in result["loto_frequency"]:
        if row["lift"] >= min_lift:
            matches[row["loto"]] = {**row, "db_loto": db_loto, "total_samples": result["total_samples"]}
    return matches


def approaching_max_cycle_matches(min_pct: int = 55) -> dict[str, dict]:
    draw_dates = _draw_dates()
    date_to_idx = _date_index(draw_dates)
    loto_hits = _all_loto_hits()
    matches: dict[str, dict] = {}
    for lot, hit_dates in loto_hits.items():
        summary = _loto_summary(hit_dates, draw_dates, date_to_idx)
        if summary["pct_of_max"] >= min_pct:
            matches[lot] = summary
    return matches


def gap_hot_matches(min_gap: int = 8) -> dict[str, dict]:
    """Lô đang gan: current_gap >= min_gap (không cần chạm max cycle)."""
    draw_dates = _draw_dates()
    date_to_idx = _date_index(draw_dates)
    loto_hits = _all_loto_hits()
    matches: dict[str, dict] = {}
    for lot, hit_dates in loto_hits.items():
        summary = _loto_summary(hit_dates, draw_dates, date_to_idx)
        if summary["current_gap"] >= min_gap:
            matches[lot] = summary
    return matches


def frequency_hot_matches(min_lift: float = 1.05) -> dict[str, dict]:
    """Lô hay về: tần suất ngày có mặt / baseline trung bình toàn bộ loto."""
    draw_dates = _draw_dates()
    date_to_idx = _date_index(draw_dates)
    loto_hits = _all_loto_hits()
    summaries: dict[str, dict] = {}
    freqs: list[float] = []
    for lot, hit_dates in loto_hits.items():
        summary = _loto_summary(hit_dates, draw_dates, date_to_idx)
        summaries[lot] = summary
        freqs.append(summary["frequency"])
    baseline = sum(freqs) / len(freqs) if freqs else 0.0
    matches: dict[str, dict] = {}
    for lot, summary in summaries.items():
        freq = summary["frequency"]
        lift = freq / baseline if baseline > 0 else 0.0
        if lift >= min_lift:
            matches[lot] = {
                **summary,
                "lift": _round_lift(lift),
                "baseline": round(baseline, 4),
                "freq_pct": round(freq * 100, 2),
            }
    return matches


DEFAULT_FREQ_WINDOWS = (30, 50, 100, 200, 300)
DE_MAX_FREQ_WINDOW_DAYS = 365 * 5  # 5 năm
DEFAULT_DE_FREQ_WINDOWS = (365, 730, 1095, DE_MAX_FREQ_WINDOW_DAYS)
FreqRankSort = Literal["hot", "cold"]


def _normalize_de_windows(windows: Optional[list[int]]) -> list[int]:
    raw = list(windows or DEFAULT_DE_FREQ_WINDOWS)
    cleaned = sorted({w for w in raw if w > 0})
    if not cleaned:
        cleaned = list(DEFAULT_DE_FREQ_WINDOWS)
    over = [w for w in cleaned if w > DE_MAX_FREQ_WINDOW_DAYS]
    if over:
        raise ValueError(f"Đề chỉ dùng window ≤ {DE_MAX_FREQ_WINDOW_DAYS} ngày (5 năm), nhận: {over}")
    return cleaned


def _loto_counts_in_window(draw_dates: list[str]) -> tuple[dict[str, int], float]:
    if not draw_dates:
        return {}, 0.0
    date_set = set(draw_dates)
    loto_hits = _all_loto_hits()
    counts: dict[str, int] = {}
    for lot in range(100):
        lot_str = f"{lot:02d}"
        counts[lot_str] = sum(1 for d in loto_hits.get(lot_str, []) if d in date_set)
    baseline = sum(counts.values()) / 100.0
    return counts, baseline


def _build_freq_rank_rows(
    counts: dict[str, int],
    window_days: int,
    baseline_count: float,
    draw_dates: list[str],
) -> list[dict]:
    date_to_idx = _date_index(draw_dates)
    loto_hits = _all_loto_hits()
    rows: list[dict] = []
    for lot, count in counts.items():
        rate = count / window_days if window_days else 0.0
        lift = count / baseline_count if baseline_count > 0 else 0.0
        summary = _loto_summary(loto_hits.get(lot, []), draw_dates, date_to_idx)
        rows.append(
            {
                "loto": lot,
                "count": count,
                "window_days": window_days,
                "rate_pct": round(rate * 100, 1),
                "baseline_count": round(baseline_count, 2),
                "lift": _round_lift(lift),
                "current_gap": summary.get("current_gap", 0),
                "last_seen": summary.get("last_seen"),
            }
        )
    return rows


def get_loto_frequency_rank(
    window: int = 30,
    limit: int = 20,
    sort: FreqRankSort = "hot",
) -> dict:
    start_ms = time.perf_counter()
    draw_dates = _draw_dates(window)
    window_days = len(draw_dates)
    counts, baseline = _loto_counts_in_window(draw_dates)
    rows = _build_freq_rank_rows(counts, window_days, baseline, draw_dates)
    rows.sort(key=lambda r: (-r["count"], -r["lift"], r["loto"]))
    hot = rows[:limit]
    cold = sorted(rows, key=lambda r: (r["count"], r["lift"], r["loto"]))[:limit]
    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
    return {
        "module": "frequency-rank",
        "type": "loto",
        "window": window,
        "window_days": window_days,
        "period_from": draw_dates[0] if draw_dates else None,
        "period_to": draw_dates[-1] if draw_dates else None,
        "baseline_count": round(baseline, 2),
        "baseline_rate_pct": round(baseline / window_days * 100, 1) if window_days else 0.0,
        "hot": hot,
        "cold": cold,
        "sort": sort,
        "meta": {"query_time_ms": elapsed_ms, "disclaimer": DISCLAIMER},
    }


def get_de_frequency_rank(
    window: int = 730,
    limit: int = 20,
    sort: FreqRankSort = "hot",
) -> dict:
    if window > DE_MAX_FREQ_WINDOW_DAYS:
        raise ValueError(f"Đề window tối đa {DE_MAX_FREQ_WINDOW_DAYS} ngày (5 năm)")
    start_ms = time.perf_counter()
    draw_dates = _draw_dates(window)
    window_days = len(draw_dates)
    if not draw_dates:
        return {
            "module": "frequency-rank",
            "type": "de",
            "window": window,
            "window_days": 0,
            "hot": [],
            "cold": [],
            "meta": {"query_time_ms": 0},
        }
    rows = fetch_all(
        """
        SELECT p.last_two AS de, COUNT(*)::int AS count
        FROM draws d
        JOIN prizes p ON p.draw_id = d.id
        WHERE d.region = 'MB'
          AND p.prize_level = 'DB'
          AND d.draw_date >= %s AND d.draw_date <= %s
        GROUP BY p.last_two
        """,
        (draw_dates[0], draw_dates[-1]),
    )
    counts = {f"{i:02d}": 0 for i in range(100)}
    for row in rows:
        counts[row["de"]] = row["count"]
    baseline = window_days / 100.0
    rank_rows: list[dict] = []
    for de, count in counts.items():
        rate = count / window_days if window_days else 0.0
        lift = count / baseline if baseline > 0 else 0.0
        rank_rows.append(
            {
                "de": de,
                "count": count,
                "window_days": window_days,
                "rate_pct": round(rate * 100, 2),
                "baseline_count": round(baseline, 2),
                "lift": _round_lift(lift),
            }
        )
    rank_rows.sort(key=lambda r: (-r["count"], -r["lift"], r["de"]))
    hot = rank_rows[:limit]
    cold = sorted(rank_rows, key=lambda r: (r["count"], r["lift"], r["de"]))[:limit]
    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
    return {
        "module": "frequency-rank",
        "type": "de",
        "window": window,
        "window_days": window_days,
        "period_from": draw_dates[0],
        "period_to": draw_dates[-1],
        "baseline_count": round(baseline, 2),
        "baseline_rate_pct": round(baseline / window_days * 100, 2) if window_days else 0.0,
        "hot": hot,
        "cold": cold,
        "sort": sort,
        "meta": {"query_time_ms": elapsed_ms, "disclaimer": DISCLAIMER},
    }


def get_loto_frequency_summary(
    windows: Optional[list[int]] = None,
    limit: int = 10,
) -> dict:
    start_ms = time.perf_counter()
    windows = windows or list(DEFAULT_DE_FREQ_WINDOWS)
    by_window: dict[str, dict] = {}
    for window in windows:
        rank = get_loto_frequency_rank(window=window, limit=limit, sort="hot")
        by_window[str(window)] = {
            "window_days": rank["window_days"],
            "period_from": rank["period_from"],
            "period_to": rank["period_to"],
            "baseline_count": rank["baseline_count"],
            "baseline_rate_pct": rank["baseline_rate_pct"],
            "hot": rank["hot"],
            "cold": rank["cold"],
        }
    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
    return {
        "module": "frequency-summary",
        "type": "loto",
        "windows": by_window,
        "meta": {"query_time_ms": elapsed_ms},
    }


def _loto_window_profiles(windows: list[int]) -> dict[str, dict[str, dict]]:
    profiles: dict[str, dict[str, dict]] = {
        f"{i:02d}": {} for i in range(100)
    }
    for window in windows:
        draw_dates = _draw_dates(window)
        window_days = len(draw_dates)
        counts, baseline = _loto_counts_in_window(draw_dates)
        for lot, count in counts.items():
            rate = count / window_days if window_days else 0.0
            profiles[lot][str(window)] = {
                "count": count,
                "rate_pct": round(rate * 100, 1),
                "lift": _round_lift(count / baseline if baseline > 0 else 0.0),
            }
    return profiles


def _trend_label(momentum_pp: float) -> str:
    if momentum_pp >= 8:
        return "heating_fast"
    if momentum_pp >= 3:
        return "heating"
    if momentum_pp <= -8:
        return "cooling_fast"
    if momentum_pp <= -3:
        return "cooling"
    return "stable"


def get_loto_frequency_trend(
    windows: Optional[list[int]] = None,
    limit: int = 20,
) -> dict:
    start_ms = time.perf_counter()
    windows = sorted(windows or list(DEFAULT_FREQ_WINDOWS))
    if len(windows) < 2:
        raise ValueError("Need at least 2 windows for trend analysis")

    short_w, long_w = windows[0], windows[-1]
    profiles = _loto_window_profiles(windows)
    rows: list[dict] = []
    for lot in sorted(profiles.keys()):
        wdata = profiles[lot]
        short_rate = wdata.get(str(short_w), {}).get("rate_pct", 0.0)
        long_rate = wdata.get(str(long_w), {}).get("rate_pct", 0.0)
        momentum = round(short_rate - long_rate, 1)
        rows.append(
            {
                "loto": lot,
                "windows": wdata,
                "momentum_pp": momentum,
                "short_window": short_w,
                "long_window": long_w,
                "trend": _trend_label(momentum),
            }
        )

    trending_up = sorted(
        [r for r in rows if r["momentum_pp"] > 0],
        key=lambda r: (-r["momentum_pp"], -r["windows"].get(str(short_w), {}).get("count", 0), r["loto"]),
    )[:limit]
    trending_down = sorted(
        [r for r in rows if r["momentum_pp"] < 0],
        key=lambda r: (r["momentum_pp"], r["windows"].get(str(short_w), {}).get("count", 0), r["loto"]),
    )[:limit]
    stable_hot = sorted(
        [
            r
            for r in rows
            if r["windows"].get(str(long_w), {}).get("rate_pct", 0) >= 30
            and r["windows"].get(str(short_w), {}).get("rate_pct", 0) >= 28
        ],
        key=lambda r: -r["windows"].get(str(short_w), {}).get("count", 0),
    )[:limit]

    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
    return {
        "module": "frequency-trend",
        "type": "loto",
        "windows": windows,
        "trending_up": trending_up,
        "trending_down": trending_down,
        "stable_hot": stable_hot,
        "meta": {
            "momentum_formula": f"rate_{short_w}d - rate_{long_w}d (điểm %)",
            "heating_threshold_pp": 3,
            "query_time_ms": elapsed_ms,
            "disclaimer": DISCLAIMER,
        },
    }


def frequency_trend_matches(
    windows: Optional[list[int]] = None,
    top_n: int = 20,
    min_momentum_pp: float = 3.0,
) -> dict[str, dict]:
    trend = get_loto_frequency_trend(windows=windows, limit=top_n)
    matches: dict[str, dict] = {}
    for row in trend["trending_up"]:
        if row["momentum_pp"] < min_momentum_pp:
            continue
        matches[row["loto"]] = {
            **row,
            "momentum": row["momentum_pp"],
            "lift": 1 + row["momentum_pp"] / 100.0,
        }
    return matches


def frequency_rank_hot_matches(
    windows: tuple[int, ...] = DEFAULT_FREQ_WINDOWS,
    top_n: int = 25,
) -> dict[str, dict]:
    """Loto thuộc top N hay về theo số lần xuất hiện trong từng cửa sổ ngày."""
    matches: dict[str, dict] = {}
    for window in windows:
        rank = get_loto_frequency_rank(window=window, limit=top_n, sort="hot")
        for row in rank["hot"]:
            lot = row["loto"]
            payload = {**row, "rank_window": window}
            if lot not in matches or row["count"] > matches[lot]["count"]:
                matches[lot] = payload
    return matches


def _de_meta(de: str) -> dict[str, str]:
    dau = de[0]
    dit = de[1]
    tong = str((int(dau) + int(dit)) % 10)
    return {"dau": dau, "dit": dit, "tong": tong}


def _de_counts_in_window(draw_dates: list[str]) -> tuple[dict[str, int], float]:
    if not draw_dates:
        return {f"{i:02d}": 0 for i in range(100)}, 0.0
    rows = fetch_all(
        """
        SELECT p.last_two AS de, COUNT(*)::int AS count
        FROM draws d
        JOIN prizes p ON p.draw_id = d.id
        WHERE d.region = 'MB'
          AND p.prize_level = 'DB'
          AND d.draw_date >= %s AND d.draw_date <= %s
        GROUP BY p.last_two
        """,
        (draw_dates[0], draw_dates[-1]),
    )
    counts = {f"{i:02d}": 0 for i in range(100)}
    for row in rows:
        counts[row["de"]] = row["count"]
    baseline = len(draw_dates) / 100.0
    return counts, baseline


def _de_window_profiles(windows: list[int]) -> dict[str, dict[str, dict]]:
    profiles: dict[str, dict[str, dict]] = {f"{i:02d}": {} for i in range(100)}
    for window in windows:
        draw_dates = _draw_dates(window)
        window_days = len(draw_dates)
        counts, baseline = _de_counts_in_window(draw_dates)
        for de, count in counts.items():
            rate = count / window_days if window_days else 0.0
            profiles[de][str(window)] = {
                "count": count,
                "rate_pct": round(rate * 100, 2),
                "lift": _round_lift(count / baseline if baseline > 0 else 0.0),
            }
    return profiles


def get_de_frequency_summary(
    windows: Optional[list[int]] = None,
    limit: int = 10,
) -> dict:
    start_ms = time.perf_counter()
    windows = _normalize_de_windows(windows)
    by_window: dict[str, dict] = {}
    for window in windows:
        rank = get_de_frequency_rank(window=window, limit=limit, sort="hot")
        hot = [{**row, **_de_meta(row["de"])} for row in rank["hot"]]
        cold = [{**row, **_de_meta(row["de"])} for row in rank["cold"]]
        by_window[str(window)] = {
            "window_days": rank["window_days"],
            "period_from": rank["period_from"],
            "period_to": rank["period_to"],
            "baseline_count": rank["baseline_count"],
            "baseline_rate_pct": rank["baseline_rate_pct"],
            "hot": hot,
            "cold": cold,
        }
    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
    return {
        "module": "frequency-summary",
        "type": "de",
        "windows": by_window,
        "meta": {"query_time_ms": elapsed_ms},
    }


DE_STABLE_HOT_LONG_RATE = 1.5
DE_STABLE_HOT_SHORT_RATE = 1.2


def get_de_frequency_trend(
    windows: Optional[list[int]] = None,
    limit: int = 20,
) -> dict:
    start_ms = time.perf_counter()
    windows = _normalize_de_windows(windows)
    if len(windows) < 2:
        raise ValueError("Need at least 2 windows for trend analysis")

    short_w, long_w = windows[0], windows[-1]
    profiles = _de_window_profiles(windows)
    rows: list[dict] = []
    for de in sorted(profiles.keys()):
        wdata = profiles[de]
        short_rate = wdata.get(str(short_w), {}).get("rate_pct", 0.0)
        long_rate = wdata.get(str(long_w), {}).get("rate_pct", 0.0)
        momentum = round(short_rate - long_rate, 2)
        rows.append(
            {
                "de": de,
                **_de_meta(de),
                "windows": wdata,
                "momentum_pp": momentum,
                "short_window": short_w,
                "long_window": long_w,
                "trend": _trend_label(momentum),
            }
        )

    trending_up = sorted(
        [r for r in rows if r["momentum_pp"] > 0],
        key=lambda r: (-r["momentum_pp"], -r["windows"].get(str(short_w), {}).get("count", 0), r["de"]),
    )[:limit]
    trending_down = sorted(
        [r for r in rows if r["momentum_pp"] < 0],
        key=lambda r: (r["momentum_pp"], r["windows"].get(str(short_w), {}).get("count", 0), r["de"]),
    )[:limit]
    stable_hot = sorted(
        [
            r
            for r in rows
            if r["windows"].get(str(long_w), {}).get("rate_pct", 0) >= DE_STABLE_HOT_LONG_RATE
            and r["windows"].get(str(short_w), {}).get("rate_pct", 0) >= DE_STABLE_HOT_SHORT_RATE
        ],
        key=lambda r: -r["windows"].get(str(short_w), {}).get("count", 0),
    )[:limit]

    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
    return {
        "module": "frequency-trend",
        "type": "de",
        "windows": windows,
        "trending_up": trending_up,
        "trending_down": trending_down,
        "stable_hot": stable_hot,
        "meta": {
            "momentum_formula": f"rate_{short_w}d - rate_{long_w}d (điểm %)",
            "heating_threshold_pp": 0.8,
            "max_window_days": DE_MAX_FREQ_WINDOW_DAYS,
            "stable_hot_threshold": {
                "short_rate_pct": DE_STABLE_HOT_SHORT_RATE,
                "long_rate_pct": DE_STABLE_HOT_LONG_RATE,
            },
            "query_time_ms": elapsed_ms,
            "disclaimer": DISCLAIMER,
        },
    }


def de_frequency_trend_matches(
    windows: Optional[list[int]] = None,
    top_n: int = 20,
    min_momentum_pp: float = 0.8,
) -> dict[str, dict]:
    trend = get_de_frequency_trend(windows=windows, limit=top_n)
    matches: dict[str, dict] = {}
    for row in trend["trending_up"]:
        if row["momentum_pp"] < min_momentum_pp:
            continue
        matches[row["de"]] = {
            **row,
            "momentum": row["momentum_pp"],
            "lift": 1 + row["momentum_pp"] / 100.0,
        }
    for row in trend["stable_hot"]:
        de = row["de"]
        if de in matches:
            continue
        short_rate = row["windows"].get(str(trend["windows"][0]), {}).get("rate_pct", 0.0)
        matches[de] = {
            **row,
            "momentum": row.get("momentum_pp", 0),
            "lift": 1 + short_rate / 100.0,
            "stable_hot": True,
        }
    return matches


def de_frequency_rank_hot_matches(
    windows: tuple[int, ...] = DEFAULT_DE_FREQ_WINDOWS,
    top_n: int = 25,
) -> dict[str, dict]:
    matches: dict[str, dict] = {}
    for window in windows:
        rank = get_de_frequency_rank(window=window, limit=top_n, sort="hot")
        for row in rank["hot"]:
            de = row["de"]
            payload = {**row, **_de_meta(de), "rank_window": window}
            if de not in matches or row["count"] > matches[de]["count"]:
                matches[de] = payload
    return matches


def _de_digit_counts_in_window(draw_dates: list[str]) -> tuple[dict[str, int], dict[str, int], int]:
    if not draw_dates:
        return {str(i): 0 for i in range(10)}, {str(i): 0 for i in range(10)}, 0
    rows = fetch_all(
        """
        SELECT
            p.first_digit::text AS dau,
            ((p.first_digit::int + p.last_digit::int) %% 10)::text AS tong,
            COUNT(*)::int AS count
        FROM draws d
        JOIN prizes p ON p.draw_id = d.id
        WHERE d.region = 'MB'
          AND p.prize_level = 'DB'
          AND p.first_digit IS NOT NULL
          AND p.last_digit IS NOT NULL
          AND d.draw_date >= %s AND d.draw_date <= %s
        GROUP BY p.first_digit, ((p.first_digit::int + p.last_digit::int) %% 10)
        """,
        (draw_dates[0], draw_dates[-1]),
    )
    dau_counts = {str(i): 0 for i in range(10)}
    tong_counts = {str(i): 0 for i in range(10)}
    for row in rows:
        dau_counts[row["dau"]] += row["count"]
        tong_counts[row["tong"]] += row["count"]
    return dau_counts, tong_counts, len(draw_dates)


def _de_digit_window_profiles(windows: list[int]) -> tuple[dict[str, dict[str, dict]], dict[str, dict[str, dict]]]:
    dau_profiles: dict[str, dict[str, dict]] = {str(i): {} for i in range(10)}
    tong_profiles: dict[str, dict[str, dict]] = {str(i): {} for i in range(10)}
    for window in windows:
        draw_dates = _draw_dates(window)
        window_days = len(draw_dates)
        dau_counts, tong_counts, _ = _de_digit_counts_in_window(draw_dates)
        dau_baseline = window_days / 10.0 if window_days else 0.0
        tong_baseline = window_days / 10.0 if window_days else 0.0
        for digit in range(10):
            d = str(digit)
            dau_rate = dau_counts[d] / window_days if window_days else 0.0
            tong_rate = tong_counts[d] / window_days if window_days else 0.0
            dau_profiles[d][str(window)] = {
                "count": dau_counts[d],
                "rate_pct": round(dau_rate * 100, 2),
                "lift": _round_lift(dau_counts[d] / dau_baseline if dau_baseline else 0.0),
            }
            tong_profiles[d][str(window)] = {
                "count": tong_counts[d],
                "rate_pct": round(tong_rate * 100, 2),
                "lift": _round_lift(tong_counts[d] / tong_baseline if tong_baseline else 0.0),
            }
    return dau_profiles, tong_profiles


def get_de_digit_trend(
    windows: Optional[list[int]] = None,
    limit: int = 5,
) -> dict:
    start_ms = time.perf_counter()
    windows = _normalize_de_windows(windows)
    if len(windows) < 2:
        raise ValueError("Need at least 2 windows for digit trend analysis")

    short_w, long_w = windows[0], windows[-1]
    dau_profiles, tong_profiles = _de_digit_window_profiles(windows)

    def _digit_rows(profiles: dict[str, dict[str, dict]], kind: str) -> list[dict]:
        rows: list[dict] = []
        for digit in sorted(profiles.keys(), key=int):
            wdata = profiles[digit]
            short_rate = wdata.get(str(short_w), {}).get("rate_pct", 0.0)
            long_rate = wdata.get(str(long_w), {}).get("rate_pct", 0.0)
            momentum = round(short_rate - long_rate, 2)
            rows.append(
                {
                    "digit": digit,
                    "kind": kind,
                    "windows": wdata,
                    "momentum_pp": momentum,
                    "short_window": short_w,
                    "long_window": long_w,
                    "trend": _trend_label(momentum),
                }
            )
        return rows

    dau_rows = _digit_rows(dau_profiles, "dau")
    tong_rows = _digit_rows(tong_profiles, "tong")
    trending_dau = sorted(
        [r for r in dau_rows if r["momentum_pp"] > 0],
        key=lambda r: (-r["momentum_pp"], -r["windows"].get(str(short_w), {}).get("count", 0), r["digit"]),
    )[:limit]
    trending_tong = sorted(
        [r for r in tong_rows if r["momentum_pp"] > 0],
        key=lambda r: (-r["momentum_pp"], -r["windows"].get(str(short_w), {}).get("count", 0), r["digit"]),
    )[:limit]
    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
    return {
        "module": "digit-trend",
        "type": "de",
        "windows": windows,
        "dau": {"trending_up": trending_dau, "all": dau_rows},
        "tong": {"trending_up": trending_tong, "all": tong_rows},
        "meta": {
            "momentum_formula": f"rate_{short_w}d - rate_{long_w}d (điểm %)",
            "query_time_ms": elapsed_ms,
            "disclaimer": DISCLAIMER,
        },
    }


def de_digit_trend_matches(
    windows: Optional[list[int]] = None,
    top_n: int = 5,
    min_momentum_pp: float = 2.0,
) -> dict[str, dict]:
    digit_trend = get_de_digit_trend(windows=windows, limit=top_n)
    hot_dau = {
        r["digit"]
        for r in digit_trend["dau"]["trending_up"]
        if r["momentum_pp"] >= min_momentum_pp
    }
    hot_tong = {
        r["digit"]
        for r in digit_trend["tong"]["trending_up"]
        if r["momentum_pp"] >= min_momentum_pp
    }
    matches: dict[str, dict] = {}
    for de in (f"{i:02d}" for i in range(100)):
        meta = _de_meta(de)
        dau_hit = meta["dau"] in hot_dau
        tong_hit = meta["tong"] in hot_tong
        if not dau_hit and not tong_hit:
            continue
        parts = []
        if dau_hit:
            dau_row = next(r for r in digit_trend["dau"]["trending_up"] if r["digit"] == meta["dau"])
            parts.append(f"đầu {meta['dau']} +{dau_row['momentum_pp']}pp")
        if tong_hit:
            tong_row = next(r for r in digit_trend["tong"]["trending_up"] if r["digit"] == meta["tong"])
            parts.append(f"tổng {meta['tong']} +{tong_row['momentum_pp']}pp")
        momentum = sum(
            r["momentum_pp"]
            for r in digit_trend["dau"]["trending_up"] + digit_trend["tong"]["trending_up"]
            if r["digit"] in (meta["dau"], meta["tong"])
            and r["momentum_pp"] >= min_momentum_pp
        )
        matches[de] = {
            **meta,
            "de": de,
            "momentum_pp": round(momentum, 2),
            "momentum": round(momentum, 2),
            "lift": 1 + momentum / 100.0,
            "digit_signals": parts,
        }
    return matches


def resolve_cf_weekday(
    db_loto: str,
    target_weekday: Optional[int],
    min_samples: int = 10,
) -> Optional[int]:
    """Dùng filter thứ chỉ khi đủ mẫu lịch sử; ngược lại bỏ filter thứ."""
    if target_weekday is None:
        return None
    probe = get_conditional_frequency(
        db_loto=db_loto,
        target_weekday=target_weekday,
        min_occ=1,
        limit=1,
    )
    if probe["total_samples"] >= min_samples:
        return target_weekday
    return None


def get_day_context(draw_date: str) -> Optional[dict]:
    row = fetch_one(
        """
        SELECT d.draw_date::text AS draw_date
        FROM draws d
        WHERE d.region = 'MB' AND d.draw_date = %s
        """,
        (draw_date,),
    )
    if not row:
        return None
    prizes = fetch_all(
        """
        SELECT p.slot_index, p.last_two, p.number,
               p.first_digit::text AS first_digit, p.last_digit::text AS last_digit
        FROM draws d JOIN prizes p ON p.draw_id = d.id
        WHERE d.region = 'MB' AND d.draw_date = %s
        ORDER BY p.slot_index
        """,
        (draw_date,),
    )
    loto_set = {p["last_two"] for p in prizes}
    de_row = next((p for p in prizes if p["slot_index"] == 0), None)
    de = de_row["last_two"] if de_row else ""
    de_dau = ""
    de_dit = ""
    if de_row:
        de_dau = de_row["first_digit"] or (de[0] if de else "")
        de_dit = de_row["last_digit"] or (de[1] if len(de) >= 2 else "")
    return {
        "draw_date": draw_date,
        "de": de,
        "de_dau": de_dau,
        "de_dit": de_dit,
        "loto_set": loto_set,
    }


def get_max_dan(
    size: int = 3,
    min_co_occur: int = 20,
    limit: int = 20,
    from_date: str = "2020-01-01",
    to_date: Optional[str] = None,
) -> dict:
    start_ms = time.perf_counter()
    from_date, to_date = _resolve_date_range(from_date, to_date)

    rows = fetch_all(
        """
        SELECT d.draw_date::text AS draw_date,
               ARRAY_AGG(DISTINCT p.last_two ORDER BY p.last_two) AS lotos
        FROM draws d JOIN prizes p ON p.draw_id = d.id
        WHERE d.region = 'MB' AND d.draw_date BETWEEN %s AND %s
        GROUP BY d.draw_date
        ORDER BY d.draw_date
        """,
        (from_date, to_date),
    )
    total_days = len(rows)
    if total_days == 0 or size < 2:
        return {
            "module": "max-dan",
            "disclaimer": DISCLAIMER,
            "params": {
                "size": size,
                "min_co_occur": min_co_occur,
                "limit": limit,
                "date_range": [from_date, to_date],
            },
            "data": [],
            "meta": {"total_days": 0, "query_time_ms": 0, "baseline_method": "P(L1)×P(L2)×..."},
        }

    loto_days: dict[str, int] = defaultdict(int)
    combo_counts: dict[tuple[str, ...], int] = defaultdict(int)
    for row in rows:
        lotos = row["lotos"]
        for lot in lotos:
            loto_days[lot] += 1
        if len(lotos) < size:
            continue
        for combo in combinations(lotos, size):
            combo_counts[combo] += 1

    data: list[dict] = []
    for combo, co_occ in combo_counts.items():
        if co_occ < min_co_occur:
            continue
        p_combo = co_occ / total_days
        baseline = 1.0
        for lot in combo:
            baseline *= loto_days[lot] / total_days
        lift = p_combo / baseline if baseline > 0 else 0.0
        data.append(
            {
                "lotos": list(combo),
                "co_occurrences": co_occ,
                "p_combo": _round_prob(p_combo),
                "baseline": _round_prob(baseline),
                "lift": _round_lift(lift),
            }
        )

    data.sort(key=lambda r: (-r["lift"], -r["co_occurrences"]))
    data = data[:limit]
    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)

    return {
        "module": "max-dan",
        "disclaimer": DISCLAIMER,
        "params": {
            "size": size,
            "min_co_occur": min_co_occur,
            "limit": limit,
            "date_range": [from_date, to_date],
        },
        "data": data,
        "meta": {
            "total_days": total_days,
            "query_time_ms": elapsed_ms,
            "baseline_method": "P(L1)×P(L2)×...",
            "total_combos": len(data),
        },
    }
