from __future__ import annotations

import json
from pathlib import Path

from app.db import fetch_all
from app.repositories.draw_repo import draw_repo
from app.services.expert_scorer import WEIGHTS_PATH, _load_weights, reload_weights

MIN_WEIGHT = 0.3
MAX_WEIGHT = 1.0


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
    if pick_type in ("dan_de", "dan_40s", "dan_36s", "dan_64s"):
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
    return any(n in lotos for n in nums)


def run_backtest(days: int = 90) -> dict:
    rows = fetch_all(
        """
        SELECT target_date::text AS target_date, username, pick_type, numbers
        FROM forum_user_picks
        WHERE target_date >= CURRENT_DATE - %s::int
        ORDER BY target_date DESC
        """,
        (days,),
    )

    stats: dict[str, dict[str, dict]] = {}
    scored_dates: set[str] = set()
    skipped_no_draw = 0

    for row in rows:
        d = row["target_date"]
        ketqua = draw_repo.get_mb_ketqua(d)
        if not ketqua:
            skipped_no_draw += 1
            continue
        scored_dates.add(d)

        user = row["username"]
        pt = row["pick_type"]
        hit = pick_hit(pt, list(row["numbers"] or []), ketqua)

        bucket = stats.setdefault(user, {}).setdefault(pt, {"hits": 0, "total": 0})
        bucket["total"] += 1
        if hit:
            bucket["hits"] += 1

    per_user: dict[str, dict] = {}
    for user, types in stats.items():
        per_user[user] = {}
        for pt, b in types.items():
            rate = b["hits"] / b["total"] if b["total"] else 0.0
            per_user[user][pt] = {
                "hits": b["hits"],
                "total": b["total"],
                "rate": round(rate, 4),
                "suggested_weight": round(max(MIN_WEIGHT, min(MAX_WEIGHT, rate)), 3),
            }

    return {
        "days": days,
        "pick_rows": len(rows),
        "dates_with_draw": len(scored_dates),
        "skipped_no_draw": skipped_no_draw,
        "users": per_user,
    }


def suggest_weights(days: int = 90, blend: float = 0.35) -> dict[str, dict[str, float]]:
    """Blend backtest rates with existing expert_weights.json."""
    current = _load_weights()
    report = run_backtest(days)
    suggested: dict[str, dict[str, float]] = {}

    all_users = set(current) | set(report["users"])
    for user in sorted(all_users):
        cur = dict(current.get(user) or {"default": 0.3})
        bt = report["users"].get(user) or {}
        merged: dict[str, float] = {}

        keys = set(cur) | set(bt)
        for key in keys:
            old = float(cur.get(key, cur.get("default", 0.3)))
            if key in bt and bt[key]["total"] >= 3:
                new = float(bt[key]["suggested_weight"])
                merged[key] = round(old * (1 - blend) + new * blend, 3)
            else:
                merged[key] = round(old, 3)
        suggested[user] = merged

    return suggested


def write_suggested_weights(days: int = 90, blend: float = 0.35) -> dict:
    suggested = suggest_weights(days=days, blend=blend)
    path = Path(WEIGHTS_PATH)
    path.write_text(json.dumps(suggested, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    reload_weights()
    return {"ok": True, "path": str(path), "user_count": len(suggested), "days": days, "blend": blend}
