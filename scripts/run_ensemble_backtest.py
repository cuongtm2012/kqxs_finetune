#!/usr/bin/env python3
"""Ensemble backtest: walk-forward validation cho toàn bộ XSMB engine.

Đo hit rate, recall, precision cho top N picks mỗi ngày.
So sánh với baseline random để biết engine có thực sự beat random không.
"""
import os
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import init_pool, fetch_all
from app.prediction.constants import TARGET_LOTO, TARGET_DE, ALL_LOTOS
from app.prediction.features import actual_values_for_date, previous_draw_date
from app.services.candidate_service import build_candidates


# ——— Config ———
TOP_N_LIST = (5, 10, 20)
DAYS = 90       # backtest over last N draws
RANDOM_SEED = 42
BUILD_LOTO_KWARGS = {"target": "loto", "top": 20, "min_filters": 1, "sort": "score"}
BUILD_DE_KWARGS = {"target": "de", "top": 10, "min_filters": 1, "sort": "score"}
RANDOM_PRECISION = 100  # iterations for random baseline


def _random_pick(pool_size: int, top_n: int) -> int:
    """How many hits would random pick get? Average over RANDOM_PRECISION runs."""
    import random
    random.seed(RANDOM_SEED)
    total = 0
    for _ in range(RANDOM_PRECISION):
        picks = set(random.sample(ALL_LOTOS, min(top_n, pool_size)))
        total += len(picks)
    return total / RANDOM_PRECISION


def run_backtest(days: int = DAYS) -> dict:
    start_ms = time.perf_counter()
    init_pool(min_size=1, max_size=1)

    # Fetch draw dates
    rows = fetch_all(
        """SELECT draw_date::text AS draw_date
           FROM draws WHERE region = 'MB'
           ORDER BY draw_date ASC LIMIT %s""",
        (days + 5,),  # +5 buffer for as_of
    )
    dates = sorted(row["draw_date"] for row in rows)
    if not dates:
        return {"error": "no_draw_data"}

    # Remove first few — need as_of date before target
    backtest_dates = dates[3:]  # skip earliest 3 (need prev draw data)
    if not backtest_dates:
        return {"error": "not_enough_dates"}

    # Stats per top_n
    top_stats: dict[int, dict] = {
        top_n: {
            "top_n": top_n,
            "days_evaluated": 0,
            "days_skipped": 0,
            "hit_days": 0,
            "total_recall": 0.0,
            "total_overlap": 0,
            "total_recommended": 0,
            "total_actual": 0,
        }
        for top_n in TOP_N_LIST
    }

    per_filter_hits: dict[str, int] = defaultdict(int)
    per_filter_total: dict[str, int] = defaultdict(int)

    for target_date in backtest_dates:
        target_dt = __import__("datetime").date.fromisoformat(target_date)
        as_of = previous_draw_date(target_dt)
        if not as_of:
            continue

        actual = actual_values_for_date(target_dt, TARGET_LOTO)
        if not actual:
            continue

        # Build candidates — predict based on as_of (yesterday's data)
        try:
            result = build_candidates(
                target_date=target_date, **BUILD_LOTO_KWARGS,
            )
        except Exception as e:
            top_stats[TOP_N_LIST[0]]["days_skipped"] += 1
            continue

        candidates = result.get("candidates", [])
        recommended = {c["loto"] for c in candidates}
        if not recommended:
            continue

        overlap = len(recommended & actual)
        for top_n in TOP_N_LIST:
            top_picks = {c["loto"] for c in candidates[:top_n]}
            top_overlap = len(top_picks & actual)
            stats = top_stats[top_n]
            stats["days_evaluated"] += 1
            stats["total_overlap"] += top_overlap
            stats["total_recommended"] += len(top_picks)
            stats["total_actual"] += len(actual)
            stats["total_recall"] += top_overlap / len(actual) if actual else 0
            if top_overlap > 0:
                stats["hit_days"] += 1

        # Per-filter hit analysis
        for c in candidates:
            for fkey in c.get("score_breakdown", {}):
                per_filter_total[fkey] += 1
                if c["loto"] in actual:
                    per_filter_hits[fkey] += 1

    # Build output
    limits_out = []
    for top_n in TOP_N_LIST:
        stats = top_stats[top_n]
        ev = stats["days_evaluated"]
        hit_rate = stats["hit_days"] / ev if ev else 0.0
        avg_recall = stats["total_recall"] / ev if ev else 0.0
        avg_overlap = stats["total_overlap"] / ev if ev else 0.0
        avg_recommended = stats["total_recommended"] / ev if ev else 0.0

        # Random baseline
        n_actual = stats["total_actual"] / ev if ev else 27
        random_hits = _random_pick(100, top_n)
        random_hit_rate = random_hits / n_actual if n_actual else 0

        limits_out.append({
            "top_n": top_n,
            "days_evaluated": ev,
            "days_skipped": stats["days_skipped"],
            "hit_rate": round(hit_rate, 4),
            "avg_recall": round(avg_recall, 4),
            "avg_overlap": round(avg_overlap, 2),
            "avg_recommended": round(avg_recommended, 1),
            "random_hit_rate": round(random_hit_rate, 4),
            "lift_vs_random": round(hit_rate / random_hit_rate, 3) if random_hit_rate else None,
            "avg_actual": round(n_actual, 1),
        })

    # Per-filter stats
    filter_stats = {}
    for fkey in sorted(per_filter_total.keys()):
        total = per_filter_total[fkey]
        hits = per_filter_hits.get(fkey, 0)
        filter_stats[fkey] = {
            "hits": hits,
            "total": total,
            "precision": round(hits / total, 4) if total else 0.0,
        }

    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
    return {
        "module": "ensemble-backtest",
        "period_from": backtest_dates[0],
        "period_to": backtest_dates[-1],
        "days_requested": days,
        "days_evaluated": len(backtest_dates),
        "top_n_results": limits_out,
        "filter_precision": filter_stats,
        "meta": {"query_time_ms": elapsed_ms},
    }


def print_report(r: dict):
    if "error" in r:
        print(f"❌ Error: {r['error']}")
        return

    print(f"📊 ENSEMBLE BACKTEST REPORT")
    print(f"   Period: {r['period_from']} → {r['period_to']}")
    print(f"   Days evaluated: {r['days_evaluated']}")
    print()

    for row in r["top_n_results"]:
        print(f"── Top {row['top_n']} ──")
        print(f"   Hit days: {row['hit_rate']*row['days_evaluated']:.0f}/{row['days_evaluated']} ({row['hit_rate']:.1%})")
        print(f"   Avg recall: {row['avg_recall']:.1%}")
        print(f"   Avg overlap: {row['avg_overlap']:.1f} numbers")
        print(f"   Random baseline hit rate: {row['random_hit_rate']:.1%}")
        print(f"   Lift vs random: {row['lift_vs_random']:.2f}x")
        print()

    print("── Filter precision ──")
    print(f"   {'Filter':>30} → {'Hits':>5}/{str('Total'):>6} {'Precision':>10}")
    print("   " + "-" * 55)
    for fkey, fs in sorted(r["filter_precision"].items(), key=lambda x: -x[1]["precision"]):
        print(f"   {fkey:>30} → {fs['hits']:>5}/{fs['total']:>5} {fs['precision']:.2%}")
    print()

    # Also run for đề
    print("── Đề backtest ──")
    run_de_backtest(r["days_evaluated"])


def run_de_backtest(days: int):
    """Lightweight đề backtest."""
    rows = fetch_all(
        """SELECT draw_date::text AS draw_date
           FROM draws WHERE region = 'MB'
           ORDER BY draw_date ASC LIMIT %s""",
        (days + 5,),
    )
    dates = sorted(row["draw_date"] for row in rows)
    backtest_dates = dates[3:]
    hits10, hits5, total = 0, 0, 0

    for target_date in backtest_dates:
        target_dt = __import__("datetime").date.fromisoformat(target_date)
        as_of = previous_draw_date(target_dt)
        if not as_of:
            continue
        actual = actual_values_for_date(target_dt, TARGET_DE)
        if not actual:
            continue
        actual_de = next(iter(actual))
        try:
            result = build_candidates(target_date=target_date, **BUILD_DE_KWARGS)
        except Exception:
            continue
        candidates = result.get("candidates", [])
        top10 = {c["loto"] for c in candidates[:10]}
        top5 = {c["loto"] for c in candidates[:5]}
        if actual_de in top10:
            hits10 += 1
        if actual_de in top5:
            hits5 += 1
        total += 1

    print(f"   Top 10 hit: {hits10}/{total} ({hits10/total:.1%})")
    print(f"   Top 5 hit:  {hits5}/{total} ({hits5/total:.1%})")
    print(f"   Random (1/100): {total/100:.1f} expected hits = {1/100:.1%}")


if __name__ == "__main__":
    r = run_backtest()
    print_report(r)
