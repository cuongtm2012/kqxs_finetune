from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any, Optional

from app.repositories.expert_winrate_repo import expert_winrate_repo
from app.repositories.forum_repo import forum_repo
from app.repositories.draw_repo import draw_repo
from app.services.expert_pick_eval import (
    evaluate_picks_by_date,
    group_picks_by_date,
    performance_pick_type_candidates,
)
from app.services.expert_scorer import canonical_username

DEFAULT_PERIOD_LABEL = os.getenv("EXPERT_PERF_PERIOD", "rolling_90d")
PERIOD_DISPLAY_LABELS = {
    "rolling_90d": "90 ngày gần nhất",
}
TZ = "Asia/Ho_Chi_Minh"
LOW_SAMPLE_THRESHOLD = 3


def parse_period_label(period_label: str) -> tuple[date, date]:
    """Parse '2026-06' → first/last day of month."""
    if len(period_label) == 7 and period_label[4] == "-":
        y, m = int(period_label[:4]), int(period_label[5:7])
        start = date(y, m, 1)
        if m == 12:
            end = date(y, 12, 31)
        else:
            end = date(y, m + 1, 1) - timedelta(days=1)
        return start, end
    if period_label == "rolling_90d":
        end = date.today()
        start = end - timedelta(days=90)
        return start, end
    raise ValueError(f"Unsupported period_label: {period_label}")


def period_display_label(period_label: str | None = None) -> str:
    label = period_label or DEFAULT_PERIOD_LABEL
    if label in PERIOD_DISPLAY_LABELS:
        return PERIOD_DISPLAY_LABELS[label]
    if len(label) == 7 and label[4] == "-":
        y, m = int(label[:4]), int(label[5:7])
        return f"Tháng {m}/{y}"
    return label


def _enrich_performance(perf: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not perf or not perf.get("total"):
        return None
    out = {
        "hits": int(perf["hits"]),
        "total": int(perf["total"]),
        "rate_pct": perf["rate_pct"],
    }
    if int(perf["total"]) < LOW_SAMPLE_THRESHOLD:
        out["low_sample"] = True
    return out


def _pick_first_performance(candidates: list[Optional[dict[str, Any]]]) -> Optional[dict[str, Any]]:
    """Return the first candidate with data — list is ordered most-specific first."""
    for perf in candidates:
        if perf and perf.get("total"):
            return _enrich_performance(perf)
    return None


def compute_period_stats(
    period_start: date,
    period_end: date,
    period_label: str,
    *,
    write_pick_results: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    rows = forum_repo.get_user_picks_range(
        period_start.isoformat(),
        period_end.isoformat(),
    )

    eval_result = evaluate_picks_by_date(
        group_picks_by_date(rows),
        draw_repo.get_mb_ketqua,
        collect_results=write_pick_results,
    )
    stats = eval_result["stats"]
    pick_results = eval_result["pick_results"]

    upserted = 0
    if not dry_run:
        expert_winrate_repo.delete_period(period_label)
        for user, types in stats.items():
            for pt, b in types.items():
                if b["total"] <= 0:
                    continue
                rate = b["hits"] / b["total"]
                expert_winrate_repo.upsert_win_rate(
                    username=user,
                    pick_type=pt,
                    period_label=period_label,
                    period_start=period_start,
                    period_end=period_end,
                    hits=b["hits"],
                    total=b["total"],
                    win_rate=round(rate, 4),
                )
                upserted += 1
        if write_pick_results and pick_results:
            expert_winrate_repo.replace_pick_results(pick_results)

    return {
        "period_label": period_label,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "rows_upserted": upserted,
        "pick_results_written": len(pick_results) if write_pick_results and not dry_run else 0,
        "skipped_no_draw": eval_result["skipped_no_draw"],
        "dates_evaluated": eval_result["dates_evaluated"],
        "users": stats,
        "dry_run": dry_run,
    }


def get_performance(
    username: str,
    pick_type: str,
    period_label: str = DEFAULT_PERIOD_LABEL,
) -> Optional[dict[str, Any]]:
    user = canonical_username(username)
    perfs = [
        expert_winrate_repo.get_performance(user, pt, period_label)
        for pt in performance_pick_type_candidates(pick_type)
    ]
    return _pick_first_performance(perfs)


def refresh_period(
    period_label: str,
    *,
    write_pick_results: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    start, end = parse_period_label(period_label)
    return compute_period_stats(
        start, end, period_label,
        write_pick_results=write_pick_results,
        dry_run=dry_run,
    )


def get_period_performance(period_label: str) -> dict[str, Any]:
    return expert_winrate_repo.get_period_snapshot(period_label)
