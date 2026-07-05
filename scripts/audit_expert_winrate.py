#!/usr/bin/env python3
"""Compare expert weights, DB win rates, and live backtest for audit."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.expert_backtest_service import run_backtest
from app.services.expert_scorer import WEIGHTS_PATH, expert_weight
from app.services.expert_winrate_service import get_performance


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit expert win rates vs weights")
    parser.add_argument("--users", required=True, help="Comma-separated usernames")
    parser.add_argument("--period", default="2026-06")
    parser.add_argument("--days", type=int, default=90)
    args = parser.parse_args()

    users = [u.strip() for u in args.users.split(",") if u.strip()]
    weights = json.loads(Path(WEIGHTS_PATH).read_text(encoding="utf-8"))
    backtest = run_backtest(args.days)["users"]

    failed = 0
    print(f"{'user':<18} {'type':<10} {'json_w':>7} {'db':>12} {'bt':>12} status")
    print("-" * 72)

    pick_types = ("stl", "btl", "dan_40s", "dan_36s", "dan_64s", "dan_de")
    for user in users:
        for pt in pick_types:
            json_w = expert_weight(user, pt)
            db = get_performance(user, pt, args.period)
            bt_bucket = backtest.get(user, {}).get(pt)
            db_s = f"{db['hits']}/{db['total']}" if db else "—"
            bt_s = f"{bt_bucket['hits']}/{bt_bucket['total']}" if bt_bucket else "—"
            status = "OK"
            if db and bt_bucket and (db["hits"], db["total"]) != (bt_bucket["hits"], bt_bucket["total"]):
                if args.period == "rolling_90d":
                    status = "DRIFT"
                    failed += 1
            if user in weights and pt in ("dan_40s", "stl") and json_w == weights[user].get("default"):
                pass
            print(f"{user:<18} {pt:<10} {json_w:>7.2f} {db_s:>12} {bt_s:>12} {status}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
