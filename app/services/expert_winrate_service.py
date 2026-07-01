from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Optional

from app.repositories.expert_winrate_repo import expert_winrate_repo
from app.repositories.forum_repo import forum_repo
from app.repositories.draw_repo import draw_repo
from app.services.expert_backtest_service import pick_hit
from app.services.expert_scorer import canonical_username

DEFAULT_PERIOD_LABEL = "2026-06"
TZ = "Asia/Ho_Chi_Minh"


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


def _draw_de(ketqua: dict) -> str:
    return (ketqua.get("kq0") or "")[-2:].zfill(2)


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

    stats: dict[str, dict[str, dict]] = {}
    pick_results: list[dict] = []
    skipped_no_draw = 0
    evaluated_dates: set[str] = set()

    by_date: dict[str, list[dict]] = {}
    for p in rows:
        d = p.get("target_date") or ""
        if not d:
            continue
        by_date.setdefault(d, []).append(p)

    def _dedupe_day(day_picks: list[dict]) -> list[dict]:
        merged: dict[tuple[str, str], dict] = {}
        for p in day_picks:
            user = canonical_username(p.get("username", ""))
            pt = p.get("pick_type", "")
            row = {**p, "username": user}
            key = (user, pt)
            prev = merged.get(key)
            if not prev or (row.get("posted_at") or "") >= (prev.get("posted_at") or ""):
                merged[key] = row
        return list(merged.values())

    for target_date, day_picks in sorted(by_date.items()):
        ketqua = draw_repo.get_mb_ketqua(target_date)
        if not ketqua:
            skipped_no_draw += len(day_picks)
            continue
        evaluated_dates.add(target_date)
        de = _draw_de(ketqua)

        for p in _dedupe_day(day_picks):
            user = p["username"]
            pt = p["pick_type"]
            nums = list(p.get("numbers") or [])
            hit = pick_hit(pt, nums, ketqua)

            bucket = stats.setdefault(user, {}).setdefault(pt, {"hits": 0, "total": 0})
            bucket["total"] += 1
            if hit:
                bucket["hits"] += 1

            if write_pick_results:
                pick_results.append({
                    "target_date": target_date,
                    "username": user,
                    "pick_type": pt,
                    "numbers": nums,
                    "hit": hit,
                    "draw_de": de,
                })

    upserted = 0
    if not dry_run:
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
        "skipped_no_draw": skipped_no_draw,
        "dates_evaluated": len(evaluated_dates),
        "users": stats,
        "dry_run": dry_run,
    }


def get_performance(
    username: str,
    pick_type: str,
    period_label: str = DEFAULT_PERIOD_LABEL,
) -> Optional[dict[str, Any]]:
    user = canonical_username(username)
    perf = expert_winrate_repo.get_performance(user, pick_type, period_label)
    if perf:
        return perf
    if pick_type != "default":
        perf = expert_winrate_repo.get_performance(user, "default", period_label)
    return perf


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
