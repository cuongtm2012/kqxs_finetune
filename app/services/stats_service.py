import time
from collections import defaultdict
from datetime import date, timedelta
from itertools import combinations
from typing import Literal, Optional

from app.db import fetch_all, fetch_one
from app.repositories.draw_repo import draw_repo

DISCLAIMER = (
    "Thống kê dựa trên dữ liệu lịch sử XSMB. "
    "KQXS dựa trên quay số ngẫu nhiên. "
    "Không có mô hình thống kê nào beat random >1.15x liên tục. "
    "Thông tin mang tính tham khảo, không đảm bảo kết quả."
)

CANDIDATES_DISCLAIMER = (
    "Stats-based candidate pool. Không phải dự đoán. Lift tối đa ~1.15x so với random."
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


def _all_loto_hits() -> dict[str, list[str]]:
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
    return grouped


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

    for i, day in enumerate(days):
        if i + window >= len(days):
            continue
        de_val = day["de"]
        if not de_val:
            continue
        if de and de_val != de:
            continue

        window_lotos: set[str] = set()
        for j in range(1, window + 1):
            window_lotos |= days[i + j]["loto_set"]

        for lot in target_lotos:
            stats[(de_val, lot)]["occurrences"] += 1
            if lot in window_lotos:
                stats[(de_val, lot)]["falls"] += 1

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


def approaching_max_cycle_matches(min_pct: int = 70) -> dict[str, dict]:
    draw_dates = _draw_dates()
    date_to_idx = _date_index(draw_dates)
    loto_hits = _all_loto_hits()
    matches: dict[str, dict] = {}
    for lot, hit_dates in loto_hits.items():
        summary = _loto_summary(hit_dates, draw_dates, date_to_idx)
        if summary["pct_of_max"] >= min_pct:
            matches[lot] = summary
    return matches


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
        SELECT p.slot_index, p.last_two, p.number
        FROM draws d JOIN prizes p ON p.draw_id = d.id
        WHERE d.region = 'MB' AND d.draw_date = %s
        ORDER BY p.slot_index
        """,
        (draw_date,),
    )
    loto_set = {p["last_two"] for p in prizes}
    de = next((p["last_two"] for p in prizes if p["slot_index"] == 0), "")
    return {"draw_date": draw_date, "de": de, "loto_set": loto_set}


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
