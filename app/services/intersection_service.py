import logging
import time
from datetime import date, timedelta
from typing import Literal, Optional

from app.db import fetch_all
from app.prediction.constants import TARGET_DE
from app.prediction.features import actual_values_for_date, latest_draw_date, previous_draw_date
from app.services.rbk_crawler import get_rbk_cau
from app.services.stats_service import get_conditional_frequency, get_day_context, resolve_cf_weekday

logger = logging.getLogger(__name__)

INTERSECTION_DISCLAIMER = (
    "Intersection Engine: kết hợp Conditional Frequency + cầu lặp. "
    "Chỉ pick khi tín hiệu đủ mạnh; có thể skip ngày yếu. Không phải dự đoán."
)

IntersectionStrategy = Literal["intersection", "cf_only", "rbk_only"]
IntersectionFallback = Literal["cf_only", "rbk_only", "none"]

DEFAULT_MIN_CF_LIFT = 3.0
DEFAULT_MIN_CAU = 4
DEFAULT_TOP = 20
DEFAULT_CAU_LIMIT = 5
DEFAULT_MIN_OCC = 1
CF_MIN_WEEKDAY_SAMPLES = 10

BACKTEST_CONFIGS = [
    {"min_cf_lift": 4.0, "min_rbk_cau": 4, "strategy": "intersection", "fallback": "none"},
    {"min_cf_lift": 4.0, "min_rbk_cau": 5, "strategy": "intersection", "fallback": "none"},
    {"min_cf_lift": 3.0, "min_rbk_cau": 5, "strategy": "intersection", "fallback": "none"},
    {"min_cf_lift": 3.0, "min_rbk_cau": 4, "strategy": "intersection", "fallback": "none"},
]


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


def _get_cf_candidates(
    db_loto: str,
    target_weekday: Optional[int],
    min_cf_lift: float,
    min_occ: int = DEFAULT_MIN_OCC,
) -> tuple[list[dict], int, Optional[int]]:
    cf_weekday = resolve_cf_weekday(db_loto, target_weekday, min_samples=CF_MIN_WEEKDAY_SAMPLES)
    result = get_conditional_frequency(
        db_loto=db_loto,
        target_weekday=cf_weekday,
        min_occ=min_occ,
        limit=100,
        sort="lift",
    )
    candidates = [
        {
            "loto": row["loto"],
            "lift": row["lift"],
            "count": row["count"],
            "pct": row["pct"],
        }
        for row in result["loto_frequency"]
        if row["lift"] >= min_cf_lift
    ]
    return candidates, result["total_samples"], cf_weekday


def _get_rbk_candidates(
    as_of_date: str,
    min_rbk_cau: int,
    rbk_limit: int = DEFAULT_CAU_LIMIT,
) -> tuple[list[str], dict[str, int], int]:
    result = get_rbk_cau(date_str=as_of_date, limit=rbk_limit, min_cau=min_rbk_cau)
    counts = dict(result.get("number_counts") or {})
    if not counts:
        for lot in result.get("recommended", []):
            counts[lot] = counts.get(lot, 1)
    rbk_list = sorted(counts.keys(), key=lambda lot: (-counts[lot], lot))
    return rbk_list, counts, int(result.get("total_cau", 0))


def _sort_pick_key(lot: str, cf_by_loto: dict[str, dict], rbk_counts: dict[str, int]) -> tuple:
    cf = cf_by_loto.get(lot, {})
    return (-float(cf.get("lift", 0)), -int(rbk_counts.get(lot, 0)), lot)


def _resolve_picks(
    strategy: IntersectionStrategy,
    fallback: IntersectionFallback,
    intersection: list[str],
    cf_candidates: list[dict],
    rbk_candidates: list[str],
    rbk_counts: dict[str, int],
    top: int,
) -> tuple[list[str], str]:
    cf_by_loto = {row["loto"]: row for row in cf_candidates}
    intersection_set = set(intersection)

    if strategy == "cf_only":
        lotos = [row["loto"] for row in cf_candidates]
        strategy_used = "cf_only"
    elif strategy == "rbk_only":
        lotos = list(rbk_candidates)
        strategy_used = "rbk_only"
    else:
        if intersection:
            lotos = list(intersection)
            strategy_used = "intersection"
        elif fallback == "cf_only":
            lotos = [row["loto"] for row in cf_candidates]
            strategy_used = "cf_only"
        elif fallback == "rbk_only":
            lotos = list(rbk_candidates)
            strategy_used = "rbk_only"
        else:
            lotos = []
            strategy_used = "none"

    lotos = sorted(lotos, key=lambda lot: _sort_pick_key(lot, cf_by_loto, rbk_counts))[:top]
    return lotos, strategy_used


def _format_final_picks(
    lotos: list[str],
    strategy_used: str,
    intersection_set: set[str],
    cf_by_loto: dict[str, dict],
    rbk_counts: dict[str, int],
) -> list[dict]:
    picks: list[dict] = []
    for lot in lotos:
        source = "intersection" if lot in intersection_set and strategy_used == "intersection" else strategy_used
        if source == "intersection" and lot not in intersection_set:
            source = strategy_used
        entry: dict = {"loto": lot, "source": source}
        if lot in cf_by_loto:
            entry["cf_lift"] = cf_by_loto[lot]["lift"]
        if lot in rbk_counts:
            entry["rbk_cau"] = rbk_counts[lot]
        picks.append(entry)
    return picks


def build_intersection(
    target_date: Optional[str] = None,
    top: int = DEFAULT_TOP,
    min_cf_lift: float = DEFAULT_MIN_CF_LIFT,
    min_rbk_cau: int = DEFAULT_MIN_CAU,
    strategy: IntersectionStrategy = "intersection",
    fallback: IntersectionFallback = "none",
    rbk_limit: int = DEFAULT_CAU_LIMIT,
    min_occ: int = DEFAULT_MIN_OCC,
) -> dict:
    start_ms = time.perf_counter()
    target_str, as_of_str = _resolve_dates(target_date)
    target_dt = date.fromisoformat(target_str)

    ctx = get_day_context(as_of_str)
    if not ctx:
        raise ValueError(f"No draw data for as_of_date {as_of_str}")

    yesterday_db = ctx["de"]
    yesterday_db_loto = yesterday_db
    weekday = target_dt.weekday()

    cf_candidates, cf_total_samples, cf_weekday = _get_cf_candidates(
        db_loto=yesterday_db_loto,
        target_weekday=weekday,
        min_cf_lift=min_cf_lift,
        min_occ=min_occ,
    )
    rbk_candidates, rbk_counts, rbk_total_cau = _get_rbk_candidates(
        as_of_str, min_rbk_cau=min_rbk_cau, rbk_limit=rbk_limit
    )

    cf_set = {row["loto"] for row in cf_candidates}
    rbk_set = set(rbk_candidates)
    intersection = sorted(cf_set & rbk_set, key=lambda lot: _sort_pick_key(lot, {r["loto"]: r for r in cf_candidates}, rbk_counts))

    pick_lotos, strategy_used = _resolve_picks(
        strategy=strategy,
        fallback=fallback,
        intersection=intersection,
        cf_candidates=cf_candidates,
        rbk_candidates=rbk_candidates,
        rbk_counts=rbk_counts,
        top=top,
    )
    cf_by_loto = {row["loto"]: row for row in cf_candidates}
    final_picks = _format_final_picks(
        pick_lotos, strategy_used, set(intersection), cf_by_loto, rbk_counts
    )

    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
    return {
        "module": "intersection",
        "target_date": target_str,
        "as_of_date": as_of_str,
        "strategy": strategy,
        "params": {
            "top": top,
            "min_cf_lift": min_cf_lift,
            "min_rbk_cau": min_rbk_cau,
            "strategy": strategy,
            "fallback": fallback,
            "rbk_limit": rbk_limit,
            "min_occ": min_occ,
        },
        "yesterday_db": yesterday_db,
        "yesterday_db_loto": yesterday_db_loto,
        "cf_candidates": cf_candidates,
        "rbk_candidates": rbk_candidates,
        "intersection": intersection,
        "final_picks": final_picks,
        "meta": {
            "cf_total_samples": cf_total_samples,
            "cf_weekday_applied": cf_weekday,
            "cf_weekday_skipped": cf_weekday is None and weekday is not None,
            "rbk_total_cau": rbk_total_cau,
            "strategy_used": strategy_used,
            "picks_count": len(final_picks),
            "disclaimer": INTERSECTION_DISCLAIMER,
            "query_time_ms": elapsed_ms,
        },
    }


def evaluate_intersection(
    target_date: str,
    top: int = DEFAULT_TOP,
    min_cf_lift: float = DEFAULT_MIN_CF_LIFT,
    min_rbk_cau: int = DEFAULT_MIN_CAU,
    strategy: IntersectionStrategy = "intersection",
    fallback: IntersectionFallback = "none",
    rbk_limit: int = DEFAULT_CAU_LIMIT,
) -> dict:
    start_ms = time.perf_counter()
    prediction = build_intersection(
        target_date=target_date,
        top=top,
        min_cf_lift=min_cf_lift,
        min_rbk_cau=min_rbk_cau,
        strategy=strategy,
        fallback=fallback,
        rbk_limit=rbk_limit,
    )
    picks = [row["loto"] for row in prediction["final_picks"]]
    actual_de = actual_values_for_date(date.fromisoformat(target_date), TARGET_DE)
    actual_loto = next(iter(actual_de), "") if actual_de else ""
    hit = actual_loto in picks if picks and actual_loto else False
    rank = picks.index(actual_loto) + 1 if hit else None

    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
    return {
        "endpoint": "intersection/evaluate",
        "target_date": target_date,
        "as_of_date": prediction["as_of_date"],
        "prediction": picks,
        "actual": {"de_loto": actual_loto},
        "metrics": {
            "primary_metric": "hit_rate",
            "hit": hit,
            "rank": rank,
            "picks_count": len(picks),
            "strategy_used": prediction["meta"]["strategy_used"],
            "skipped": len(picks) == 0,
        },
        "meta": {"query_time_ms": elapsed_ms, "disclaimer": INTERSECTION_DISCLAIMER},
    }


def _random_hit_rate(avg_picks: float) -> float:
    if avg_picks <= 0:
        return 0.01
    return 1 - (99 / 100) ** avg_picks


def _backtest_one_config(
    target_dates: list[date],
    min_cf_lift: float,
    min_rbk_cau: int,
    strategy: IntersectionStrategy,
    fallback: IntersectionFallback,
    top: int,
    rbk_limit: int,
) -> dict:
    signal_days = 0
    hits = 0
    total_picks = 0

    for target_dt in target_dates:
        if previous_draw_date(target_dt) is None:
            continue
        try:
            result = build_intersection(
                target_date=target_dt.isoformat(),
                top=top,
                min_cf_lift=min_cf_lift,
                min_rbk_cau=min_rbk_cau,
                strategy=strategy,
                fallback=fallback,
                rbk_limit=rbk_limit,
            )
        except ValueError:
            continue

        picks = [row["loto"] for row in result["final_picks"]]
        if not picks:
            continue

        actual_de = actual_values_for_date(target_dt, TARGET_DE)
        actual_loto = next(iter(actual_de), "") if actual_de else ""
        if not actual_loto:
            continue

        signal_days += 1
        total_picks += len(picks)
        if actual_loto in picks:
            hits += 1

    avg_picks = total_picks / signal_days if signal_days else 0.0
    hit_rate = hits / signal_days if signal_days else 0.0
    random_rate = _random_hit_rate(avg_picks)
    lift = hit_rate / random_rate if random_rate > 0 else 0.0

    return {
        "min_cf_lift": min_cf_lift,
        "min_rbk_cau": min_rbk_cau,
        "strategy": strategy,
        "fallback": fallback,
        "signal_days": signal_days,
        "total_days": len(target_dates),
        "avg_picks": round(avg_picks, 1),
        "hit_rate": round(hit_rate, 4),
        "lift": round(lift, 2),
    }


def run_intersection_backtest(
    days: int = 30,
    top: int = DEFAULT_TOP,
    min_cf_lift: Optional[float] = None,
    min_rbk_cau: Optional[int] = None,
    strategy: IntersectionStrategy = "intersection",
    fallback: IntersectionFallback = "none",
    rbk_limit: int = DEFAULT_CAU_LIMIT,
    compare_strategies: bool = True,
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
    if not target_dates:
        return {
            "module": "intersection-backtest",
            "days_requested": days,
            "configs": [],
            "meta": {"query_time_ms": 0, "error": "no_draw_data"},
        }

    configs: list[dict] = []
    if min_cf_lift is not None and min_rbk_cau is not None:
        configs.append(
            _backtest_one_config(
                target_dates, min_cf_lift, min_rbk_cau, strategy, fallback, top, rbk_limit
            )
        )
    else:
        for cfg in BACKTEST_CONFIGS:
            configs.append(_backtest_one_config(target_dates, top=top, rbk_limit=rbk_limit, **cfg))

    if compare_strategies:
        for strat in ("cf_only", "rbk_only"):
            label_strategy: IntersectionStrategy = strat
            configs.append(
                _backtest_one_config(
                    target_dates,
                    min_cf_lift=DEFAULT_MIN_CF_LIFT,
                    min_rbk_cau=DEFAULT_MIN_CAU,
                    strategy=label_strategy,
                    fallback="none",
                    top=top,
                    rbk_limit=rbk_limit,
                )
            )
        for min_cau in (3, 4, 5, 6):
            configs.append(
                _backtest_one_config(
                    target_dates,
                    min_cf_lift=0.0,
                    min_rbk_cau=min_cau,
                    strategy="rbk_only",
                    fallback="none",
                    top=top,
                    rbk_limit=rbk_limit,
                )
            )

    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
    best = max(configs, key=lambda c: (c["lift"], c["signal_days"]), default=None)
    return {
        "module": "intersection-backtest",
        "period_from": target_dates[0].isoformat(),
        "period_to": target_dates[-1].isoformat(),
        "days_requested": days,
        "days_evaluated": len(target_dates),
        "target": "de_loto",
        "configs": configs,
        "best_config": best,
        "meta": {
            "query_time_ms": elapsed_ms,
            "disclaimer": INTERSECTION_DISCLAIMER,
            "note": "Lift vs random với cùng avg_picks trên ngày có tín hiệu (đề loto)",
        },
    }
