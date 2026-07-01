#!/usr/bin/env python3
"""Backtest forum picks vs XSMB draws and optionally refresh expert_weights.json."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import init_pool
from app.services.expert_backtest_service import run_backtest, suggest_weights, write_suggested_weights


def main() -> int:
    parser = argparse.ArgumentParser(description="Backtest forum expert picks")
    parser.add_argument("--days", type=int, default=90, help="Lookback window")
    parser.add_argument("--blend", type=float, default=0.35, help="Blend ratio for weight refresh")
    parser.add_argument("--write", action="store_true", help="Write blended weights to expert_weights.json")
    parser.add_argument("--json", action="store_true", help="Print full JSON report")
    args = parser.parse_args()

    init_pool()

    report = run_backtest(args.days)
    if args.json:
        payload = {"backtest": report}
        if args.write:
            payload["write"] = write_suggested_weights(days=args.days, blend=args.blend)
        else:
            payload["suggested"] = suggest_weights(days=args.days, blend=args.blend)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"Backtest {args.days} ngày — {report['pick_rows']} picks, {report['dates_with_draw']} ngày có KQ")
    if report["skipped_no_draw"]:
        print(f"  (bỏ qua {report['skipped_no_draw']} pick không có KQ)")

    for user, types in sorted(report["users"].items()):
        for pt, b in sorted(types.items()):
            print(
                f"  {user:20} {pt:8} {b['hits']:2}/{b['total']:2} "
                f"({b['rate']*100:5.1f}%) → w={b['suggested_weight']}"
            )

    if args.write:
        result = write_suggested_weights(days=args.days, blend=args.blend)
        print(f"\nĐã ghi {result['user_count']} users → {result['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
