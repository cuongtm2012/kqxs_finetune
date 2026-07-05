from __future__ import annotations

import json
from pathlib import Path

from app.db import fetch_all
from app.repositories.draw_repo import draw_repo
from app.services.expert_pick_eval import evaluate_picks_by_date, group_picks_by_date, pick_hit
from app.services.expert_scorer import WEIGHTS_PATH, _load_weights, reload_weights

MIN_WEIGHT = 0.3
MAX_WEIGHT = 1.0


def run_backtest(days: int = 90) -> dict:
    rows = fetch_all(
        """
        SELECT target_date::text AS target_date, username, pick_type, numbers,
               posted_at::text AS posted_at
        FROM forum_user_picks
        WHERE target_date >= CURRENT_DATE - %s::int
        ORDER BY target_date DESC
        """,
        (days,),
    )

    eval_result = evaluate_picks_by_date(
        group_picks_by_date([dict(r) for r in rows]),
        draw_repo.get_mb_ketqua,
    )
    stats = eval_result["stats"]

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
        "dates_with_draw": eval_result["dates_evaluated"],
        "skipped_no_draw": eval_result["skipped_no_draw"],
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
