import logging
import random
import time
from collections import defaultdict
from datetime import date, timedelta
from typing import Literal, Optional

from app.db import fetch_all
from app.prediction.constants import TARGET_LOTO
from app.prediction.features import actual_values_for_date, latest_draw_date, previous_draw_date
from app.services.stats_service import (
    CANDIDATES_DISCLAIMER,
    WEEKDAYS_VI,
    approaching_max_cycle_matches,
    calendar_bias_matches,
    get_day_context,
    get_lo_roi,
    get_pairs,
)

logger = logging.getLogger(__name__)

CandidateSort = Literal["score", "filters", "loto"]
FilterMatch = tuple[str, str, Optional[dict]]

FILTER_KEYS = {
    "lag-1 pair": "lag-1",
    "same-day pair": "same-day",
    "max-cycle": "max-cycle",
    "calendar bias": "calendar",
    "lo-roi": "lo-roi",
}


def _score_contribution(filter_name: str, detail: dict) -> float:
    key = FILTER_KEYS[filter_name]
    lift = float(detail.get("lift", 1))
    if key in ("lag-1", "same-day"):
        return min((lift - 1) * 2, 0.5)
    if key == "max-cycle":
        return detail.get("pct_of_max", 0) / 100.0
    if key == "calendar":
        return min((lift - 1) * 3, 0.5)
    if key == "lo-roi":
        return (lift - 1) * 1
    return 0.0


def _compute_score(breakdown: dict[str, float]) -> float:
    return round(sum(breakdown.values()), 2)


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
        if y in yesterday_lotos and x not in seen:
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
        if y in yesterday_lotos and x not in seen:
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
        reason = (
            f"max-cycle: current gap {summary['current_gap']}/{summary['max_gap_hist']} ngày "
            f"({summary['pct_of_max']}%)"
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
            f"lô rơi: sau đề {yesterday_de} loto {row['loto']} rơi {row['prob']:.1%} "
            f"(lift {row['lift']}x)"
        )
        matches.append((row["loto"], reason, row))
    return matches


def _sort_candidates(candidates: list[dict], sort: CandidateSort) -> list[dict]:
    if sort == "score":
        return sorted(candidates, key=lambda c: (-c["score"], c["loto"]))
    if sort == "filters":
        return sorted(candidates, key=lambda c: (-c["filters_matched"], -c["score"], c["loto"]))
    return sorted(candidates, key=lambda c: c["loto"])


def build_candidates(
    target_date: Optional[str] = None,
    top: int = 20,
    min_filters: int = 1,
    sort: CandidateSort = "score",
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

    loto_filters: dict[str, dict[str, dict]] = defaultdict(dict)
    filters_applied = []

    for filter_def in filter_defs:
        filter_name = filter_def["name"]
        filter_key = FILTER_KEYS[filter_name]
        matched = filter_def["fn"]()
        per_filter: dict[str, FilterMatch] = {}
        for lot, reason, detail in matched:
            if lot not in per_filter:
                per_filter[lot] = (lot, reason, detail)

        filter_matches = list(per_filter.values())
        filters_applied.append(
            {
                "name": filter_name,
                **{k: v for k, v in filter_def.items() if k not in ("name", "fn")},
                "matched": len(filter_matches),
            }
        )
        for lot, reason, detail in filter_matches:
            contribution = round(_score_contribution(filter_name, detail or {}), 2)
            loto_filters[lot][filter_key] = {
                "reason": reason,
                "score_contribution": contribution,
                "detail": detail,
            }

    candidates = []
    for lot, filters in loto_filters.items():
        if len(filters) < min_filters:
            continue
        breakdown = {k: v["score_contribution"] for k, v in filters.items()}
        entry = {
            "loto": lot,
            "score": _compute_score(breakdown),
            "filters_matched": len(filters),
            "score_breakdown": breakdown,
        }
        if include_reasons:
            entry["reasons"] = [filters[k]["reason"] for k in sorted(filters.keys())]
        if include_pair_detail:
            entry["filter_details"] = {k: filters[k]["detail"] for k in filters}
        candidates.append(entry)

    candidates = _sort_candidates(candidates, sort)[:top]

    avg_filters = (
        round(sum(c["filters_matched"] for c in candidates) / len(candidates), 1)
        if candidates
        else 0.0
    )
    avg_score = round(sum(c["score"] for c in candidates) / len(candidates), 2) if candidates else 0.0
    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
    if elapsed_ms > 1000:
        logger.warning("candidates query slow: %dms target_date=%s", elapsed_ms, target_str)

    return {
        "endpoint": "candidates",
        "target_date": target_str,
        "as_of_date": as_of_str,
        "disclaimer": CANDIDATES_DISCLAIMER,
        "context": {
            "yesterday_lotos": sorted(yesterday_lotos),
            "yesterday_de": yesterday_de,
            "target_weekday": WEEKDAYS_VI[weekday],
        },
        "candidates": candidates,
        "filters_applied": filters_applied,
        "meta": {
            "total_candidates": len(candidates),
            "total_lotos_scanned": len(loto_filters),
            "filters_run": len(filter_defs),
            "avg_filters_per_candidate": avg_filters,
            "avg_score": avg_score,
            "scoring_method": "lift-weighted (mỗi filter scale khác nhau)",
            "sort": sort,
            "query_time_ms": elapsed_ms,
        },
    }


def _evaluate_candidate_day(candidate_lotos: list[str], actual: set[str]) -> tuple[float, float]:
    pred = set(candidate_lotos)
    overlap = len(pred & actual)
    hit = 1.0 if overlap > 0 else 0.0
    recall = overlap / len(actual) if actual else 0.0
    return hit, recall


def _random_baseline_loto(top_k: int, trials: int = 5000) -> tuple[float, float]:
    hit_sum = 0.0
    recall_sum = 0.0
    for _ in range(trials):
        picked = {f"{v:02d}" for v in random.sample(range(100), top_k)}
        actual = {f"{v:02d}" for v in random.sample(range(100), 27)}
        hit, recall = _evaluate_candidate_day(list(picked), actual)
        hit_sum += hit
        recall_sum += recall
    return hit_sum / trials, recall_sum / trials


def _backtest_config(
    target_dates: list[date],
    top: int,
    min_filters: int,
    sort: CandidateSort,
) -> dict:
    hit_sum = 0.0
    recall_sum = 0.0
    evaluated = 0
    for target_dt in target_dates:
        if previous_draw_date(target_dt) is None:
            continue
        try:
            result = build_candidates(
                target_date=target_dt.isoformat(),
                top=top,
                min_filters=min_filters,
                sort=sort,
                include_reasons=False,
            )
        except ValueError:
            continue
        candidates = [c["loto"] for c in result["candidates"]]
        if not candidates:
            continue
        actual = actual_values_for_date(target_dt, TARGET_LOTO)
        if not actual:
            continue
        hit, recall = _evaluate_candidate_day(candidates, actual)
        hit_sum += hit
        recall_sum += recall
        evaluated += 1
    return {
        "days_evaluated": evaluated,
        "hit_rate": hit_sum / evaluated if evaluated else 0.0,
        "recall": recall_sum / evaluated if evaluated else 0.0,
    }


def run_candidates_backtest(
    days: int = 90,
    top: int = 20,
    min_filters: int = 1,
) -> dict:
    start_ms = time.perf_counter()
    rows = fetch_all(
        """
        SELECT draw_date::text AS d FROM draws
        WHERE region = 'MB' ORDER BY draw_date DESC LIMIT %s
        """,
        (days,),
    )
    target_dates = [date.fromisoformat(r["d"]) for r in reversed(rows)]

    rand_hit, rand_recall = _random_baseline_loto(top)
    results = []

    configs = sorted({min_filters, 1, 2, 3})
    for mf in configs:
        sort_mode: CandidateSort = "score" if mf == 1 else "filters"
        stats = _backtest_config(target_dates, top, mf, sort_mode)
        lift = stats["recall"] / rand_recall if rand_recall > 0 else 0.0
        results.append(
            {
                "model": f"candidates (min_filters={mf}, sort={sort_mode})",
                f"hit_rate@{top}": round(stats["hit_rate"], 3),
                f"recall@{top}": round(stats["recall"], 3),
                "lift": round(lift, 2),
                "days_evaluated": stats["days_evaluated"],
            }
        )

    results.append(
        {
            "model": "random_baseline",
            f"hit_rate@{top}": round(rand_hit, 3),
            f"recall@{top}": round(rand_recall, 3),
            "lift": 1.0,
        }
    )

    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
    return {
        "module": "candidates",
        "type": "backtest",
        "disclaimer": CANDIDATES_DISCLAIMER,
        "params": {"days": days, "top": top, "min_filters": min_filters},
        "results": results,
        "meta": {
            "query_time_ms": elapsed_ms,
            "date_range": [target_dates[0].isoformat(), target_dates[-1].isoformat()] if target_dates else [],
        },
    }
