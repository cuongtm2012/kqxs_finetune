import time
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from app.prediction.features import latest_draw_date, previous_draw_date
from app.services.stats_service import (
    CANDIDATES_DISCLAIMER,
    approaching_max_cycle_matches,
    calendar_bias_matches,
    get_day_context,
    get_lo_roi,
    get_pairs,
)

FilterMatch = tuple[str, str, Optional[dict]]


def _resolve_dates(target_date: Optional[str]) -> tuple[str, str]:
    latest = latest_draw_date()
    if latest is None:
        raise ValueError("No MB draw data available")

    if target_date:
        target = date.fromisoformat(target_date)
        as_of = previous_draw_date(target)
        if as_of is None:
            as_of = latest
    else:
        as_of = latest
        target = as_of + timedelta(days=1)

    return target.isoformat(), as_of.isoformat()


def _lag1_matches(yesterday_lotos: set[str], min_lift: float = 1.10) -> list[FilterMatch]:
    result = get_pairs(pair_type="lag-1", min_lift=min_lift, min_occ=30, limit=500, sort="lift")
    total_days = result["params"]["total_days"]
    matches: list[FilterMatch] = []
    seen: set[str] = set()

    for row in result["data"]:
        x, y = row["x"], row["y"]
        if x in yesterday_lotos and y not in seen:
            reason = (
                f"lag-1: {x} hôm qua → {y} có P={row['p_xy']:.1%} "
                f"(lift {row['lift']}x, baseline {row['baseline']:.1%})"
            )
            detail = {**row, "from_loto": x, "total_days": total_days}
            matches.append((y, reason, detail))
            seen.add(y)
        elif y in yesterday_lotos and x not in seen:
            reason = (
                f"lag-1: {y} hôm qua → {x} có P={row['p_xy']:.1%} "
                f"(lift {row['lift']}x, baseline {row['baseline']:.1%})"
            )
            detail = {**row, "from_loto": y, "total_days": total_days}
            matches.append((x, reason, detail))
            seen.add(x)
    return matches


def _same_day_matches(yesterday_lotos: set[str], min_lift: float = 1.10) -> list[FilterMatch]:
    result = get_pairs(pair_type="same-day", min_lift=min_lift, min_occ=30, limit=500, sort="lift")
    total_days = result["params"]["total_days"]
    matches: list[FilterMatch] = []
    seen: set[str] = set()

    for row in result["data"]:
        x, y = row["x"], row["y"]
        if x in yesterday_lotos and y not in seen:
            reason = (
                f"same-day: ({x},{y}) cùng về {row['co_occurrences']}/{total_days} ngày "
                f"(lift {row['lift']}x)"
            )
            matches.append((y, reason, row))
            seen.add(y)
        elif y in yesterday_lotos and x not in seen:
            reason = (
                f"same-day: ({x},{y}) cùng về {row['co_occurrences']}/{total_days} ngày "
                f"(lift {row['lift']}x)"
            )
            matches.append((x, reason, row))
            seen.add(x)
    return matches


def _max_cycle_matches(min_pct: int = 70) -> list[FilterMatch]:
    matches: list[FilterMatch] = []
    for lot, summary in approaching_max_cycle_matches(min_pct=min_pct).items():
        gaps = summary["gaps"]
        cur_gap = summary["current_gap"]
        times_exceeded = sum(1 for g in gaps if g > cur_gap)
        reason = (
            f"max-cycle: current gap {cur_gap}/{summary['max_gap_hist']} ngày "
            f"({summary['pct_of_max']}% max cycle, chỉ vượt {times_exceeded} lần)"
        )
        matches.append((lot, reason, summary))
    return matches


def _calendar_matches(weekday: int, min_lift: float = 1.05) -> list[FilterMatch]:
    matches: list[FilterMatch] = []
    for lot, info in calendar_bias_matches(weekday, min_lift=min_lift).items():
        reason = (
            f"calendar: {info['weekday'].lower()} loto {lot} tần suất {info['prob']:.1%} "
            f"(lift {info['lift']}x)"
        )
        matches.append((lot, reason, info))
    return matches


def _lo_roi_matches(yesterday_de: str, window: int = 3) -> list[FilterMatch]:
    if not yesterday_de:
        return []
    result = get_lo_roi(de=yesterday_de, window=window, limit=200)
    matches: list[FilterMatch] = []
    for row in result["data"]:
        if row["lift"] <= 1.0:
            continue
        reason = (
            f"lo-roi: sau đề {yesterday_de} loto {row['loto']} rơi {row['falls']}/{row['occurrences']} "
            f"(prob {row['prob']:.1%}, lift {row['lift']}x)"
        )
        matches.append((row["loto"], reason, row))
    return matches


def build_candidates(
    target_date: Optional[str] = None,
    top: int = 20,
    min_filters: int = 2,
    include_reasons: bool = True,
    include_pair_detail: bool = False,
) -> dict:
    start_ms = time.perf_counter()
    target_str, as_of_str = _resolve_dates(target_date)
    target_dt = date.fromisoformat(target_str)

    ctx = get_day_context(as_of_str)
    if not ctx:
        raise ValueError(f"No draw data for as_of_date {as_of_str}")

    yesterday_lotos = ctx["loto_set"]
    yesterday_de = ctx["de"]
    weekday = target_dt.weekday()

    filter_defs = [
        {"name": "lag-1 pair", "min_lift": 1.10, "fn": lambda: _lag1_matches(yesterday_lotos)},
        {"name": "same-day pair", "min_lift": 1.10, "fn": lambda: _same_day_matches(yesterday_lotos)},
        {"name": "max-cycle", "min_pct": 70, "fn": lambda: _max_cycle_matches()},
        {"name": "calendar bias", "min_lift": 1.05, "fn": lambda: _calendar_matches(weekday)},
        {"name": "lo-roi", "window": 3, "fn": lambda: _lo_roi_matches(yesterday_de)},
    ]

    candidate_reasons: dict[str, list[str]] = defaultdict(list)
    candidate_details: dict[str, dict] = defaultdict(dict)
    filters_applied = []

    for filter_def in filter_defs:
        matched = filter_def["fn"]()
        per_filter: dict[str, FilterMatch] = {}
        for lot, reason, detail in matched:
            if lot not in per_filter:
                per_filter[lot] = (lot, reason, detail)

        filter_matches = list(per_filter.values())
        filters_applied.append(
            {
                "name": filter_def["name"],
                **{k: v for k, v in filter_def.items() if k not in ("name", "fn")},
                "matched": len(filter_matches),
            }
        )
        for lot, reason, detail in filter_matches:
            candidate_reasons[lot].append(reason)
            if include_pair_detail and detail:
                candidate_details[lot][filter_def["name"]] = detail

    candidates = []
    for lot, reasons in candidate_reasons.items():
        if len(reasons) < min_filters:
            continue
        entry = {
            "loto": lot,
            "filters_matched": len(reasons),
        }
        if include_reasons:
            entry["reasons"] = reasons
        if include_pair_detail:
            entry["filter_details"] = candidate_details.get(lot, {})
        candidates.append(entry)

    candidates.sort(key=lambda c: (-c["filters_matched"], c["loto"]))
    candidates = candidates[:top]

    avg_filters = (
        round(sum(c["filters_matched"] for c in candidates) / len(candidates), 1)
        if candidates
        else 0.0
    )
    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)

    return {
        "endpoint": "candidates",
        "target_date": target_str,
        "as_of_date": as_of_str,
        "disclaimer": CANDIDATES_DISCLAIMER,
        "context": {
            "yesterday_lotos": sorted(yesterday_lotos),
            "yesterday_de": yesterday_de,
            "target_weekday": weekday,
        },
        "candidates": candidates,
        "filters_applied": filters_applied,
        "meta": {
            "total_candidates": len(candidates),
            "total_lotos_scanned": len(candidate_reasons),
            "filters_run": len(filter_defs),
            "avg_filters_per_candidate": avg_filters,
            "query_time_ms": elapsed_ms,
        },
    }
