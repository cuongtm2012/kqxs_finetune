#!/usr/bin/env python3
"""Backfill forum picks for a calendar month (e.g. 2026-06) into forum_user_picks."""

from __future__ import annotations

import argparse
import calendar
import json
from datetime import date

from app.db import init_pool
from app.repositories.forum_repo import forum_repo
from app.services.forum_crawl_service import (
    RawPost,
    crawl_thread_all_pages,
    discover_daily_thread_slug,
    expand_chan_nuoi_posts_by_lan,
    infer_monthly_thread_slugs,
    posts_to_session_dict,
)
from app.services.forum_ingest_service import ingest_collect_session


def iter_month_days(year: int, month: int) -> list[date]:
    _, last = calendar.monthrange(year, month)
    return [date(year, month, day) for day in range(1, last + 1)]


def backfill_month(
    year: int,
    month: int,
    *,
    dry_run: bool = False,
    skip_existing: bool = False,
) -> dict:
    thread_slugs = infer_monthly_thread_slugs(year, month)

    cached_chan_nuoi: list[tuple[str, str, RawPost]] = []
    for slug in thread_slugs.values():
        for raw in crawl_thread_all_pages(slug):
            cached_chan_nuoi.append(("chan_nuoi", slug, raw))

    chan_nuoi_by_date = expand_chan_nuoi_posts_by_lan(cached_chan_nuoi, year, month)

    daily_cache: dict[str, list[tuple[str, str, RawPost]]] = {}

    summary = {
        "month": f"{year}-{month:02d}",
        "days_attempted": 0,
        "days_ingested": 0,
        "days_skipped_sunday": 0,
        "days_skipped_existing": 0,
        "days_skipped_no_posts": 0,
        "days_skipped_no_thread": 0,
        "pick_rows_total": 0,
        "chan_nuoi_posts_cached": len(cached_chan_nuoi),
        "chan_nuoi_lan_days": len(chan_nuoi_by_date),
        "errors": [],
    }

    for day in iter_month_days(year, month):
        if day.weekday() == 6:
            summary["days_skipped_sunday"] += 1
            continue

        target = day.isoformat()
        summary["days_attempted"] += 1

        if skip_existing and forum_repo.has_session(target):
            summary["days_skipped_existing"] += 1
            continue

        if target not in daily_cache:
            slug = discover_daily_thread_slug(target, "thao_luan")
            posts = crawl_thread_all_pages(slug) if slug else []
            daily_cache[target] = [("thao_luan", slug, raw) for raw in posts] if slug else []
            if not slug:
                summary["days_skipped_no_thread"] += 1

        raw_for_day = list(daily_cache.get(target, [])) + list(chan_nuoi_by_date.get(target, []))
        session = posts_to_session_dict(target, raw_for_day)
        if not session["posts"]:
            summary["days_skipped_no_posts"] += 1
            continue

        if dry_run:
            summary["days_ingested"] += 1
            summary["pick_rows_total"] += len(session["posts"])
            continue

        try:
            result = ingest_collect_session(session)
            summary["days_ingested"] += 1
            summary["pick_rows_total"] += int(result.get("pick_count", 0))
        except Exception as e:
            summary["errors"].append(f"{target}: {e}")

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill forum picks for a month")
    parser.add_argument("--month", required=True, help="YYYY-MM e.g. 2026-06")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-existing", action="store_true")
    args = parser.parse_args()

    year, month = map(int, args.month.split("-"))
    init_pool(min_size=1, max_size=2)
    result = backfill_month(
        year, month,
        dry_run=args.dry_run,
        skip_existing=args.skip_existing,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
