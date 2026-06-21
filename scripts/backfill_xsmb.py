#!/usr/bin/env python3
"""Backfill full XSMB history from xskt.com.vn into PostgreSQL."""
import argparse
import logging
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.db import init_pool  # noqa: E402
from app.repositories.draw_repo import draw_repo  # noqa: E402
from app.services.mb_import_service import import_mb_day  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backfill_xsmb")


def run(start: date, end: date, delay: float, skip_existing: bool) -> dict:
    stats = {"ok": 0, "skip": 0, "fail": 0}
    total = (end - start).days + 1
    done = 0
    current = end

    while current >= start:
        day_str = current.isoformat()
        done += 1
        if skip_existing and draw_repo.has_mb_draw(day_str):
            stats["skip"] += 1
            logger.info("[%d/%d] skip %s", done, total, day_str)
        elif import_mb_day(day_str):
            stats["ok"] += 1
            logger.info("[%d/%d] ok %s", done, total, day_str)
        else:
            stats["fail"] += 1
            logger.warning("[%d/%d] fail %s", done, total, day_str)

        if done % 100 == 0:
            draw_repo.save_checkpoint("xsmb_full", day_str, stats)

        if delay > 0:
            time.sleep(delay)
        current -= timedelta(days=1)

    draw_repo.save_checkpoint("xsmb_full", start.isoformat(), stats)
    if stats["ok"]:
        draw_repo.refresh_loto_view()
    return stats


def main():
    parser = argparse.ArgumentParser(description="Backfill XSMB into PostgreSQL")
    parser.add_argument("--from", dest="from_date", default="2007-01-01")
    parser.add_argument("--to", dest="to_date", default=date.today().isoformat())
    parser.add_argument("--delay", type=float, default=settings.scrape_delay_seconds)
    parser.add_argument("--no-skip-existing", action="store_true")
    args = parser.parse_args()

    init_pool()
    start = date.fromisoformat(args.from_date)
    end = date.fromisoformat(args.to_date)

    logger.info("Backfill XSMB %s -> %s (delay=%ss)", start, end, args.delay)
    stats = run(start, end, args.delay, skip_existing=not args.no_skip_existing)

    logger.info("=== SUMMARY === ok=%d skip=%d fail=%d", stats["ok"], stats["skip"], stats["fail"])
    logger.info("DB range: %s", draw_repo.mb_date_range())


if __name__ == "__main__":
    main()
