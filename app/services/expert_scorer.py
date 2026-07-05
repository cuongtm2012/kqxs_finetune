from __future__ import annotations

import json
import logging
import math
import os
from functools import lru_cache
from pathlib import Path

from app.services.expert_pick_eval import (
    DAN_FAMILY,
    DE_META_FAMILY,
    LOTO_FAMILY,
    performance_pick_type_candidates,
)

logger = logging.getLogger(__name__)

WEIGHTS_PATH = Path(__file__).resolve().parent.parent / "data" / "expert_weights.json"
ALIASES_PATH = Path(__file__).resolve().parent.parent / "data" / "expert_aliases.json"
DEFAULT_UNKNOWN = 0.3
SCORING_MODES = frozenset({"weight", "measured", "blend"})
DEFAULT_SCORING_MODE = os.getenv("EXPERT_SCORING_MODE", "blend")
MIN_SAMPLE = int(os.getenv("EXPERT_MIN_SAMPLE", "5"))
BLEND_PRIOR = float(os.getenv("EXPERT_BLEND_PRIOR", "0.35"))
WILSON_Z = float(os.getenv("EXPERT_WILSON_Z", "1.96"))
MAX_WEIGHT = 1.0


def wilson_lower(hits: int, total: int, z: float = WILSON_Z) -> float:
    """Wilson score interval lower bound; conservative hit rate."""
    if total <= 0:
        return 0.5
    p = hits / total
    n = float(total)
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = p + z2 / (2.0 * n)
    margin = z * math.sqrt(p * (1.0 - p) / n + z2 / (4.0 * n * n))
    return max(0.0, min(1.0, (centre - margin) / denom))


def _default_period_label() -> str:
    from app.services.expert_winrate_service import DEFAULT_PERIOD_LABEL

    return DEFAULT_PERIOD_LABEL


def _sample_ramp(total: int) -> float:
    if total <= 0:
        return 0.0
    return min(1.0, total / MIN_SAMPLE)


def expert_effective_weight(
    username: str,
    pick_type: str,
    *,
    mode: str = DEFAULT_SCORING_MODE,
    period_label: str | None = None,
) -> float:
    """Blend manual W with measured Wilson rate for recommendation scoring."""
    if mode not in SCORING_MODES:
        mode = DEFAULT_SCORING_MODE
    w_manual = expert_weight(username, pick_type)
    if mode == "weight":
        return round(min(MAX_WEIGHT, w_manual), 3)

    period = period_label or _default_period_label()
    perf = expert_performance(username, pick_type, period)
    total = int(perf["total"]) if perf else 0
    hits = int(perf["hits"]) if perf else 0
    ramp = _sample_ramp(total)

    if mode == "measured":
        if not perf:
            return round(DEFAULT_UNKNOWN, 3)
        rate = wilson_lower(hits, total)
        effective = rate * ramp + DEFAULT_UNKNOWN * (1.0 - ramp)
        return round(min(MAX_WEIGHT, max(0.0, effective)), 3)

    measured_factor = wilson_lower(hits, total) if perf else 0.5
    blend_factor = BLEND_PRIOR + (1.0 - BLEND_PRIOR) * measured_factor * ramp
    effective = w_manual * blend_factor
    return round(min(MAX_WEIGHT, max(0.0, effective)), 3)


@lru_cache(maxsize=1)
def _load_aliases() -> dict[str, str]:
    if not ALIASES_PATH.exists():
        return {}
    with open(ALIASES_PATH, encoding="utf-8") as f:
        raw = json.load(f)
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


def _user_is_dan_only(user: dict) -> bool:
    keys = set(user.keys()) - {"default"}
    has_dan = bool(keys & DAN_FAMILY) or "dan_de" in user
    has_loto = bool(keys & LOTO_FAMILY)
    has_de_meta = bool(keys & DE_META_FAMILY)
    return has_dan and not has_loto and not has_de_meta


def expert_weight(username: str, pick_type: str = "default") -> float:
    weights = _load_weights()
    user_key = canonical_username(username)
    user = weights.get(user_key) or weights.get(user_key.strip())
    if not user:
        return DEFAULT_UNKNOWN
    if pick_type in user:
        return float(user[pick_type])

    if pick_type in DAN_FAMILY:
        if "dan_de" in user:
            return float(user["dan_de"])
        if "default" in user:
            return float(user["default"])

    if pick_type in LOTO_FAMILY:
        for key in LOTO_FAMILY:
            if key in user:
                return float(user[key])
        if _user_is_dan_only(user):
            return DEFAULT_UNKNOWN
        if "default" in user:
            return float(user["default"])

    if pick_type in DE_META_FAMILY:
        if "default" in user and not _user_is_dan_only(user):
            return float(user["default"])

    if "default" in user:
        return float(user["default"])
    return DEFAULT_UNKNOWN


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


def _pick_first_backtest_stats(bucket: dict, pick_type: str) -> dict | None:
    for pt in performance_pick_type_candidates(pick_type):
        stats = bucket.get(pt)
        if stats and stats.get("total"):
            return stats
    return None


def _is_calendar_period(period_label: str) -> bool:
    return len(period_label) == 7 and period_label[4] == "-"


def expert_performance(
    username: str,
    pick_type: str,
    period_label: str | None = None,
) -> dict | None:
    from app.services.expert_winrate_service import get_performance as db_get_performance

    if period_label is None:
        period_label = _default_period_label()
    perf = db_get_performance(username, pick_type, period_label)
    if perf:
        return perf
    if _is_calendar_period(period_label):
        return None
    try:
        users = _backtest_users_snapshot()
        user_key = canonical_username(username)
        bucket = users.get(user_key) or {}
        stats = _pick_first_backtest_stats(bucket, pick_type)
        if stats and stats.get("total"):
            rate = float(stats["rate"])
            out = {
                "hits": int(stats["hits"]),
                "total": int(stats["total"]),
                "rate_pct": round(rate * 100, 1),
            }
            if int(stats["total"]) < 3:
                out["low_sample"] = True
            return out
    except Exception:
        logger.exception("expert_performance failed for username=%s", username)
    return None


def live_experts(
    picks: list[dict],
    *,
    scoring_mode: str = DEFAULT_SCORING_MODE,
    period_label: str | None = None,
) -> list[dict]:
    period = period_label or _default_period_label()
    rows = []
    for p in dedupe_picks_by_user(picks):
        pt = p.get("pick_type", "default")
        user = p["username"]
        w = expert_weight(user, pt)
        eff = expert_effective_weight(
            user, pt, mode=scoring_mode, period_label=period,
        )
        perf = expert_performance(user, pt, period)
        rows.append({
            "user": user,
            "pick_type": pt,
            "numbers": p.get("numbers") or [],
            "weight": round(w, 3),
            "effective_weight": eff,
            "performance": perf,
            "posted_at": p.get("posted_at"),
            "forum": p.get("forum"),
            "post_id": p.get("post_id"),
            "thread_id": p.get("thread_id"),
            "thread_url": p.get("thread_url"),
        })
    if scoring_mode == "weight":
        rows.sort(key=lambda x: (-x["weight"], x["user"]))
    else:
        rows.sort(key=lambda x: (-x["effective_weight"], x["user"]))
    return rows
