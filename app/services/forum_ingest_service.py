from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import logging

from app.repositories.forum_repo import forum_repo
from app.services.expert_scorer import canonical_username

logger = logging.getLogger(__name__)


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        ms = value if value > 1e11 else value * 1000
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            logger.exception("_parse_ts failed for value: %s", value)
            return None
    return None


def _infer_dan_pick_type(numbers: list, thread_id: str = "", raw: str = "") -> str:
    count = len(numbers)
    blob = f"{thread_id} {raw}".lower()
    if "64s" in blob or "64 s" in blob:
        return "dan_64s"
    if "36s" in blob or "36 s" in blob:
        return "dan_36s"
    if "40s" in blob or "40 s" in blob:
        return "dan_40s"
    if count >= 58:
        return "dan_64s"
    if count >= 38:
        return "dan_40s"
    if count >= 30:
        return "dan_36s"
    return "dan_de"


def _dan_size_label(pick_type: str) -> str:
    return {"dan_40s": "40s", "dan_36s": "36s", "dan_64s": "64s"}.get(pick_type, "dàn")


def _extract_pick_rows(posts: dict[str, Any]) -> dict[tuple[str, str], dict]:
    """Keep latest post per (username, pick_type)."""
    latest: dict[tuple[str, str], dict] = {}

    for post in posts.values():
        user = canonical_username(post.get("user", "").strip())
        if not user:
            continue
        picks = post.get("picks") or {}
        forum = post.get("forum")
        post_id = post.get("post_id")
        posted_at = _parse_ts(post.get("posted_at_ms") or post.get("posted_at"))
        raw = (post.get("raw_content") or "")[:300]

        def consider(pick_type: str, numbers: list[str]) -> None:
            if not numbers:
                return
            key = (user, pick_type)
            row = {
                "username": user,
                "pick_type": pick_type,
                "numbers": [str(n) for n in numbers],
                "forum": forum,
                "post_id": post_id,
                "posted_at": posted_at.isoformat() if posted_at else None,
                "raw_excerpt": raw,
                "_ts": posted_at or datetime.min.replace(tzinfo=timezone.utc),
            }
            if key not in latest or row["_ts"] >= latest[key]["_ts"]:
                latest[key] = row

        if picks.get("stl"):
            consider("stl", picks["stl"])
        if picks.get("btl"):
            consider("btl", picks["btl"])
        if picks.get("std_de"):
            consider("std_de", [str(x).zfill(2) for x in picks["std_de"]])
        if picks.get("btd_de"):
            consider("btd_de", [str(x).zfill(2) for x in picks["btd_de"]])
        de = picks.get("de") or {}
        if de.get("cham"):
            consider("de_cham", [str(x) for x in de["cham"]])
        if de.get("tong"):
            consider("de_tong", [str(x) for x in de["tong"]])
        if de.get("dau"):
            consider("de_dau", [str(x) for x in de["dau"]])
        if picks.get("btd"):
            consider("btd", [str(x).zfill(2) for x in picks["btd"]])
        if picks.get("btd_dau"):
            consider("btd_dau", [str(x) for x in picks["btd_dau"]])
        if picks.get("de_list"):
            consider("de_list", [str(x).zfill(2) for x in picks["de_list"]])
        if picks.get("dan_de"):
            ext_pt = picks.get("dan_pick_type")
            if ext_pt in ("dan_40s", "dan_36s", "dan_64s"):
                dan_pt = ext_pt
            else:
                dan_pt = _infer_dan_pick_type(
                    picks["dan_de"],
                    post.get("thread_id") or "",
                    raw,
                )
            consider(dan_pt, picks["dan_de"])
        muc = picks.get("muc_lo") or {}
        if muc.get(0):
            consider("muc_lo", muc[0])

    for row in latest.values():
        row.pop("_ts", None)
    return latest


def ingest_collect_session(body: dict) -> dict:
    target_date = body.get("target_date") or body.get("summary", {}).get("target_date")
    if not target_date:
        raise ValueError("target_date required")

    posts = body.get("posts") or {}
    pick_map = _extract_pick_rows(posts)
    picks = list(pick_map.values())

    forum_repo.upsert_session(
        target_date=target_date,
        window_start=body.get("window_start"),
        window_end=body.get("window_end"),
        finalized_at=body.get("finalized_at"),
        payload=body,
    )
    count = forum_repo.replace_user_picks(target_date, picks)

    return {
        "ok": True,
        "target_date": target_date,
        "pick_count": count,
        "post_count": len(posts),
    }
