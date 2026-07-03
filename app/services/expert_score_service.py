"""Score forum expert picks against XSMB draw (picks before 18:00 ICT)."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app.repositories.draw_repo import draw_repo
from app.repositories.expert_winrate_repo import expert_winrate_repo
from app.repositories.forum_repo import forum_repo
from app.services.expert_backtest_service import pick_hit
from app.services.expert_scorer import canonical_username
from app.services.mketqua_service import import_mb_from_mketqua
from app.services.mb_import_service import import_mb_day

logger = logging.getLogger(__name__)
TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def draw_cutoff_iso(target_date: str) -> str:
    """Last valid pick time for a draw day: 18:00 ICT on target_date."""
    y, m, d = map(int, target_date.split("-"))
    dt = datetime(y, m, d, 18, 0, 0, tzinfo=TZ)
    return dt.isoformat()


def _parse_posted_at(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        return dt.astimezone(TZ)
    except ValueError:
        return None


def _before_cutoff(posted_at: Optional[str], target_date: str) -> bool:
    """Pick must be posted strictly before 18:00 on draw day (ICT)."""
    dt = _parse_posted_at(posted_at)
    if not dt:
        return True
    y, m, d = map(int, target_date.split("-"))
    cutoff = datetime(y, m, d, 18, 0, 0, tzinfo=TZ)
    return dt < cutoff


def _dedupe_before_cutoff(day_picks: list[dict], target_date: str) -> list[dict]:
    merged: dict[tuple[str, str], dict] = {}
    for p in day_picks:
        if not _before_cutoff(p.get("posted_at"), target_date):
            continue
        user = canonical_username(p.get("username", ""))
        pt = p.get("pick_type", "")
        row = {**p, "username": user}
        key = (user, pt)
        prev = merged.get(key)
        if not prev or (row.get("posted_at") or "") >= (prev.get("posted_at") or ""):
            merged[key] = row
    return list(merged.values())


def _draw_de(ketqua: dict) -> str:
    return (ketqua.get("kq0") or "")[-2:].zfill(2)


def import_draw_for_day(target_date: str, *, prefer_mketqua: bool = True) -> bool:
    if prefer_mketqua and import_mb_from_mketqua(target_date):
        return True
    return import_mb_day(target_date)


def score_draw_day(
    target_date: str,
    *,
    write_results: bool = True,
    require_draw: bool = True,
) -> dict[str, Any]:
    """
    Compare forum picks for target_date (posted before 18:00 ICT) with XSMB draw.
    Persists rows to expert_pick_results when write_results=True.
    """
    ketqua = draw_repo.get_mb_ketqua(target_date)
    if not ketqua:
        if require_draw:
            return {
                "target_date": target_date,
                "ok": False,
                "error": "no_draw",
                "cutoff": draw_cutoff_iso(target_date),
            }
        return {"target_date": target_date, "ok": False, "error": "no_draw"}

    day_picks = forum_repo.get_user_picks(target_date)
    eligible = _dedupe_before_cutoff(day_picks, target_date)
    de = _draw_de(ketqua)

    results: list[dict] = []
    hits = 0
    for p in eligible:
        pt = p.get("pick_type", "")
        nums = list(p.get("numbers") or [])
        hit = pick_hit(pt, nums, ketqua)
        if hit:
            hits += 1
        results.append({
            "username": p["username"],
            "pick_type": pt,
            "numbers": nums,
            "hit": hit,
            "posted_at": p.get("posted_at"),
            "forum": p.get("forum"),
            "thread_url": p.get("thread_url"),
        })

    results.sort(key=lambda r: (not r["hit"], r["username"], r["pick_type"]))

    if write_results and results:
        pick_rows = [
            {
                "target_date": target_date,
                "username": r["username"],
                "pick_type": r["pick_type"],
                "numbers": r["numbers"],
                "hit": r["hit"],
                "draw_de": de,
            }
            for r in results
        ]
        expert_winrate_repo.replace_pick_results(pick_rows)

    total = len(results)
    return {
        "target_date": target_date,
        "ok": True,
        "cutoff": draw_cutoff_iso(target_date),
        "draw": {
            "de": de,
            "db": ketqua.get("kq0"),
            "loto": ketqua.get("kqAr") or [],
            "source": "mketqua",
        },
        "summary": {
            "hits": hits,
            "total": total,
            "hit_rate_pct": round(hits / total * 100, 1) if total else 0.0,
            "skipped_after_cutoff": len(day_picks) - len(eligible),
        },
        "results": results,
    }


def run_daily_settlement(
    target_date: Optional[str] = None,
    *,
    prefer_mketqua: bool = True,
) -> dict[str, Any]:
    """Import KQXS (mketqua first) then score forum picks — intended for 18:31 ICT."""
    if not target_date:
        target_date = datetime.now(TZ).date().isoformat()

    if datetime.now(TZ).weekday() == 6:
        return {"target_date": target_date, "ok": False, "error": "sunday_skip"}

    imported = import_draw_for_day(target_date, prefer_mketqua=prefer_mketqua)
    if imported:
        draw_repo.refresh_loto_view()

    scored = score_draw_day(target_date, write_results=True, require_draw=True)
    scored["imported"] = imported
    return scored


def get_scored_day(target_date: str) -> dict[str, Any]:
    """Read persisted score + live recompute metadata."""
    rows = expert_winrate_repo.get_pick_results(target_date)
    ketqua = draw_repo.get_mb_ketqua(target_date)
    if not rows and not ketqua:
        return {
            "target_date": target_date,
            "ok": False,
            "error": "not_scored",
            "cutoff": draw_cutoff_iso(target_date),
        }

    hits = sum(1 for r in rows if r.get("hit"))
    total = len(rows)
    return {
        "target_date": target_date,
        "ok": bool(rows),
        "cutoff": draw_cutoff_iso(target_date),
        "draw": {
            "de": _draw_de(ketqua) if ketqua else None,
            "db": ketqua.get("kq0") if ketqua else None,
            "loto": (ketqua or {}).get("kqAr") or [],
        },
        "summary": {
            "hits": hits,
            "total": total,
            "hit_rate_pct": round(hits / total * 100, 1) if total else 0.0,
        },
        "results": rows,
    }
