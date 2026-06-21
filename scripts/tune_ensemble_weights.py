#!/usr/bin/env python3
"""Tune ensemble weights from walk-forward backtest and save results."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import init_pool  # noqa: E402
from app.prediction.tuning import tune_all  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Tune ensemble weights")
    parser.add_argument("--from", dest="from_date", default="2020-01-01")
    parser.add_argument("--to", dest="to_date", default="2025-12-31")
    parser.add_argument("--samples", type=int, default=3000)
    parser.add_argument("-o", "--output", default="app/prediction/tuned_weights.json")
    args = parser.parse_args()

    init_pool()
    result = tune_all(args.from_date, args.to_date, n_samples=args.samples)
    out = ROOT / args.output
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    from app.prediction.weights import reload_tuned_weights

    reload_tuned_weights()
    print(json.dumps(result, indent=2))
    print(f"\nSaved -> {out}")


if __name__ == "__main__":
    main()
