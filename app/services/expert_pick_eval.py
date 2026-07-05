from __future__ import annotations

import re
from typing import Any, Callable, Optional

DAN_FAMILY = frozenset({"dan_de", "dan_40s", "dan_36s", "dan_64s"})
LOTO_FAMILY = frozenset({"stl", "btl", "muc_lo"})
DE_META_FAMILY = frozenset({
    "de_cham", "de_dau", "de_tong", "btd", "btd_dau", "btd_de", "std_de",
})

DAN_FAMILY_ORDER = ("dan_40s", "dan_36s", "dan_64s", "dan_de")


def _norm_nums(numbers: list[str]) -> list[str]:
    out = []
    for n in numbers:
        s = str(n).strip()
        if not s:
            continue
        out.append(s.zfill(2) if len(s) <= 2 else s)
    return out


def pick_hit(pick_type: str, numbers: list[str], ketqua: dict) -> bool:
    lotos = set(ketqua.get("kqAr") or [])
    de = (ketqua.get("kq0") or "")[-2:].zfill(2)
    nums = _norm_nums(numbers)

    if pick_type in ("stl", "btl", "muc_lo"):
        return any(n in lotos for n in nums)
    if pick_type in DAN_FAMILY:
        return de in nums
    if pick_type == "de_cham":
        tail = str(int(de) % 10)
        return tail in {str(x) for x in numbers}
    if pick_type == "de_tong":
        try:
            tong = (int(de[0]) + int(de[1])) % 10
            return str(tong) in {str(x) for x in numbers}
        except ValueError:
            return False
    if pick_type == "de_dau":
        return de[0] in {str(x) for x in numbers}
    if pick_type == "btd":
        de_norm = de.zfill(2) if de else ""
        return de_norm in {str(x).zfill(2) for x in numbers}
    if pick_type == "btd_dau":
        return de[0] in {str(x) for x in numbers}
    if pick_type == "btd_de":
        de_norm = de.zfill(2) if de else ""
        return de_norm in {str(x).zfill(2) for x in numbers}
    if pick_type == "std_de":
        de_norm = de.zfill(2) if de else ""
        for token in numbers:
            parts = re.split(r"[-/,]", str(token))
            pair = [p.strip().zfill(2) for p in parts if p.strip().isdigit()]
            if de_norm in pair:
                return True
        return False
    if pick_type == "de_list":
        de_norm = de.zfill(2) if de else ""
        return de_norm in {str(x).zfill(2) for x in numbers}
    return any(n in lotos for n in nums)


def dedupe_day_picks(day_picks: list[dict]) -> list[dict]:
    """Canonical username + latest posted_at per (user, pick_type) for one draw day."""
    from app.services.expert_scorer import canonical_username

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


def group_picks_by_date(rows: list[dict]) -> dict[str, list[dict]]:
    by_date: dict[str, list[dict]] = {}
    for p in rows:
        d = p.get("target_date") or ""
        if not d:
            continue
        by_date.setdefault(d, []).append(p)
    return by_date


def performance_pick_type_candidates(pick_type: str) -> list[str]:
    """Ordered pick_type keys to try when resolving win rate."""
    out: list[str] = []
    for pt in (pick_type,):
        if pt and pt not in out:
            out.append(pt)
    if pick_type in DAN_FAMILY or pick_type == "dan_de":
        for pt in DAN_FAMILY_ORDER:
            if pt not in out:
                out.append(pt)
    if "default" not in out:
        out.append("default")
    return out


def _draw_de(ketqua: dict) -> str:
    return (ketqua.get("kq0") or "")[-2:].zfill(2)


def evaluate_picks_by_date(
    picks_by_date: dict[str, list[dict]],
    draw_lookup: Callable[[str], Optional[dict]],
    *,
    collect_results: bool = False,
) -> dict[str, Any]:
    stats: dict[str, dict[str, dict]] = {}
    pick_results: list[dict] = []
    skipped_no_draw = 0
    evaluated_dates: set[str] = set()

    for target_date, day_picks in sorted(picks_by_date.items()):
        ketqua = draw_lookup(target_date)
        if not ketqua:
            skipped_no_draw += len(day_picks)
            continue
        evaluated_dates.add(target_date)
        de = _draw_de(ketqua)

        for p in dedupe_day_picks(day_picks):
            user = p["username"]
            pt = p.get("pick_type", "")
            nums = list(p.get("numbers") or [])
            hit = pick_hit(pt, nums, ketqua)

            bucket = stats.setdefault(user, {}).setdefault(pt, {"hits": 0, "total": 0})
            bucket["total"] += 1
            if hit:
                bucket["hits"] += 1

            if collect_results:
                pick_results.append({
                    "target_date": target_date,
                    "username": user,
                    "pick_type": pt,
                    "numbers": nums,
                    "hit": hit,
                    "draw_de": de,
                })

    return {
        "stats": stats,
        "pick_results": pick_results,
        "skipped_no_draw": skipped_no_draw,
        "dates_evaluated": len(evaluated_dates),
        "evaluated_dates": evaluated_dates,
    }
