from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

WEIGHTS_PATH = Path(__file__).resolve().parent.parent / "data" / "expert_weights.json"
ALIASES_PATH = Path(__file__).resolve().parent.parent / "data" / "expert_aliases.json"
DEFAULT_UNKNOWN = 0.3


@lru_cache(maxsize=1)
def _load_aliases() -> dict[str, str]:
    if not ALIASES_PATH.exists():
        return {}
    with open(ALIASES_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    # case-insensitive lookup
    return {str(k).strip().lower(): str(v).strip() for k, v in raw.items()}


def canonical_username(username: str) -> str:
    key = (username or "").strip()
    if not key:
        return key
    aliases = _load_aliases()
    return aliases.get(key.lower(), key)


def dedupe_picks_by_user(picks: list[dict]) -> list[dict]:
    """Gộp pick theo tài khoản chính — alias cùng người chỉ tính 1 lần."""
    merged: dict[tuple[str, str], dict] = {}
    for p in picks:
        user = canonical_username(p.get("username", ""))
        pt = p.get("pick_type", "")
        row = {**p, "username": user}
        key = (user, pt)
        prev = merged.get(key)
        if not prev or (row.get("posted_at") or "") >= (prev.get("posted_at") or ""):
            merged[key] = row
    return list(merged.values())


@lru_cache(maxsize=1)
def _load_weights() -> dict:
    with open(WEIGHTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def reload_weights() -> None:
    _load_weights.cache_clear()


def expert_weight(username: str, pick_type: str = "default") -> float:
    weights = _load_weights()
    user_key = canonical_username(username)
    user = weights.get(user_key) or weights.get(user_key.strip())
    if not user:
        return DEFAULT_UNKNOWN
    if pick_type in user:
        return float(user[pick_type])
    return float(user.get("default", DEFAULT_UNKNOWN))


def weighted_number_scores(picks: list[dict]) -> dict[str, dict]:
    """Aggregate weighted score per number from normalized picks."""
    scores: dict[str, dict] = {}
    for p in picks:
        user = p["username"]
        w = expert_weight(user, p.get("pick_type", "default"))
        for num in p.get("numbers") or []:
            n = str(num).zfill(2) if len(str(num)) <= 2 else str(num)
            if n not in scores:
                scores[n] = {"score": 0.0, "users": []}
            scores[n]["score"] += w
            if user not in scores[n]["users"]:
                scores[n]["users"].append(user)
    return scores


@lru_cache(maxsize=1)
def _backtest_users_snapshot() -> dict:
    from app.services.expert_backtest_service import run_backtest

    return run_backtest(90).get("users", {})


def expert_performance(
    username: str,
    pick_type: str,
    period_label: str = "2026-06",
) -> dict | None:
    from app.services.expert_winrate_service import get_performance as db_get_performance

    perf = db_get_performance(username, pick_type, period_label)
    if perf:
        return {"hits": perf["hits"], "total": perf["total"], "rate_pct": perf["rate_pct"]}
    try:
        users = _backtest_users_snapshot()
        user_key = canonical_username(username)
        bucket = users.get(user_key) or {}
        stats = bucket.get(pick_type) or bucket.get("default")
        if stats and stats.get("total"):
            rate = float(stats["rate"])
            return {
                "hits": int(stats["hits"]),
                "total": int(stats["total"]),
                "rate_pct": round(rate * 100, 1),
            }
    except Exception:
        logger.exception("expert_winrate failed for expert_username=%s", expert_username)
        pass
    return None


def live_experts(picks: list[dict]) -> list[dict]:
    rows = []
    for p in dedupe_picks_by_user(picks):
        pt = p.get("pick_type", "default")
        user = p["username"]
        w = expert_weight(user, pt)
        perf = expert_performance(user, pt)
        rows.append({
            "user": user,
            "pick_type": pt,
            "numbers": p.get("numbers") or [],
            "weight": round(w, 3),
            "performance": perf,
            "posted_at": p.get("posted_at"),
            "forum": p.get("forum"),
            "post_id": p.get("post_id"),
            "thread_id": p.get("thread_id"),
            "thread_url": p.get("thread_url"),
        })
    rows.sort(key=lambda x: (-x["weight"], x["user"]))
    return rows
