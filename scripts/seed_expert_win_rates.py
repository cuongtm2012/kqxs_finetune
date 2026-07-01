#!/usr/bin/env python3
"""Compute expert win rates from forum_user_picks + XSMB draws and persist to DB."""

from __future__ import annotations

import argparse
import json
import sys

from app.db import init_pool
from app.services.expert_winrate_service import refresh_period


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed expert win rates into DB")
    parser.add_argument("--period", default="2026-06", help="Period label e.g. 2026-06")
    parser.add_argument("--write-pick-results", action="store_true", help="Write expert_pick_results audit rows")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    init_pool(min_size=1, max_size=2)
    result = refresh_period(
        args.period,
        write_pick_results=args.write_pick_results,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
