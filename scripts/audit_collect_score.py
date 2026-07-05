#!/usr/bin/env python3
"""Audit forum winners vs forum_user_picks vs score for a draw day."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import init_pool
from app.repositories.draw_repo import draw_repo
from app.repositories.expert_winrate_repo import expert_winrate_repo
from app.repositories.forum_repo import forum_repo
from app.services.expert_pick_eval import pick_hit
from app.services.forum_crawl_service import (
    extract_posts_from_html,
    fetch_html,
    get_last_page,
    parse_picks,
    window_bounds_ms,
)


def _hit_types(picks: dict, ketqua: dict) -> list[str]:
    hits = []
    for pt, nums in picks.items():
        if pt in ("de", "dan_pick_type", "muc_lo"):
            continue
        if isinstance(nums, list) and nums and pick_hit(str(pt), [str(n) for n in nums], ketqua):
            hits.append(str(pt))
        elif isinstance(nums, dict):
            for sub, vals in nums.items():
                if vals and pick_hit(f"de_{sub}", [str(v) for v in vals], ketqua):
                    hits.append(f"de_{sub}")
    return hits


def audit_date(target_date: str, thread_slug: str | None) -> int:
    init_pool(1, 2)
    ketqua = draw_repo.get_mb_ketqua(target_date)
    if not ketqua:
        print(f"No draw for {target_date}")
        return 1

    start_ms, end_ms = window_bounds_ms(target_date)
    db_picks = forum_repo.get_user_picks(target_date)
    db_post_ids = {p.get("post_id") for p in db_picks if p.get("post_id")}
    score_rows = expert_winrate_repo.get_pick_results(target_date)
    score_hits = {(r["username"], r["pick_type"]) for r in score_rows if r.get("hit")}

    session = forum_repo.get_session(target_date)
    if session:
        cov = session.get("payload", {}).get("threads", {})
        print("Coverage:", {k: {
            "backfill_complete": v.get("backfill_complete"),
            "lowest": v.get("lowest_page_fetched"),
            "last": v.get("last_page_fetched"),
        } for k, v in cov.items() if k in ("thao_luan", "mo_bat")})

    if not thread_slug:
        print("No thread slug — skip forum crawl")
        return 0

    url_base = f"https://forumketqua.net/threads/{thread_slug}/"
    first = fetch_html(url_base)
    last = get_last_page(first)
    missing = []

    for page in range(1, last + 1):
        html = first if page == 1 else fetch_html(f"{url_base}page-{page}")
        for post in extract_posts_from_html(html):
            if not (start_ms <= post.posted_at_ms < end_ms):
                continue
            picks = parse_picks(post.raw_content)
            if not picks:
                continue
            hit_types = _hit_types(picks, ketqua)
            if not hit_types:
                continue
            in_db = post.post_id in db_post_ids
            in_score = any(
                (post.user, pt) in score_hits
                for pt in hit_types
            )
            if not in_db or not in_score:
                missing.append({
                    "user": post.user,
                    "post_id": post.post_id,
                    "page": page,
                    "hits": hit_types,
                    "in_db": in_db,
                    "in_score": in_score,
                    "picks": picks,
                })

    if not missing:
        print(f"OK {target_date}: no missing STL/BTL/de winners in window")
        return 0

    print(f"GAPS {target_date}: {len(missing)} winner post(s) missing from DB/score")
    for m in missing:
        print(
            f"  {m['user']} post {m['post_id']} p{m['page']} "
            f"hits={m['hits']} db={m['in_db']} score={m['in_score']} picks={m['picks']}"
        )
    return 1


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True, help="YYYY-MM-DD")
    p.add_argument("--thread-slug", default="", help="e.g. thao-luan-du-doan-xsmb-thu-7-ngay-04-7-2026.101405")
    args = p.parse_args()
    raise SystemExit(audit_date(args.date, args.thread_slug or None))


if __name__ == "__main__":
    main()
