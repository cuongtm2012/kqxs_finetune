#!/usr/bin/env python3
"""Compare recommendation scoring across modes for audit."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.expert_scorer import expert_effective_weight, expert_performance, expert_weight
from app.services.forum_recommendation_service import build_recommendations


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit recommendation scoring modes")
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--users", default="")
    parser.add_argument("--modes", default="weight,blend,measured")
    args = parser.parse_args()

    users = [u.strip() for u in args.users.split(",") if u.strip()]
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    failed = 0

    for mode in modes:
        data = build_recommendations(args.target_date, scoring_mode=mode)
        print(f"\n=== scoring_mode={mode} btl_lo={data['picks'].get('btl_lo')} ===")
        if data.get("forum_loto_top10"):
            top = data["forum_loto_top10"][0]
            print(f"  top loto: {top['loto']} score={top['score']}")

        for e in data.get("live_experts", []):
            if users and e["user"] not in users:
                continue
            perf = expert_performance(e["user"], e["pick_type"])
            perf_s = f"{perf['hits']}/{perf['total']}" if perf else "—"
            eff = e.get("effective_weight", expert_effective_weight(
                e["user"], e["pick_type"], mode=mode,
            ))
            print(
                f"  {e['user']:<14} {e['pick_type']:<8} "
                f"w={expert_weight(e['user'], e['pick_type']):.2f} "
                f"eff={eff:.2f} perf={perf_s}"
            )
            if mode == "blend" and not perf and expert_weight(e["user"], e["pick_type"]) > 0.5:
                if eff >= expert_weight(e["user"], e["pick_type"]) * 0.99:
                    print("    FAIL: blend should gate high manual W without perf")
                    failed += 1

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
