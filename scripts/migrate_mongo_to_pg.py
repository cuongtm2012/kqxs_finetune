#!/usr/bin/env python3
"""One-time migration: MongoDB ketqua -> PostgreSQL draws/prizes."""
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from pymongo import MongoClient
except ImportError:
    print("Install pymongo temporarily: pip install pymongo")
    sys.exit(1)

from app.db import init_pool  # noqa: E402
from app.repositories.draw_repo import draw_repo  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migrate")


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--mongo-host", default="127.0.0.1")
    parser.add_argument("--mongo-port", type=int, default=27017)
    parser.add_argument("--mongo-db", default="kqxs")
    args = parser.parse_args()

    init_pool()
    client = MongoClient(args.mongo_host, args.mongo_port)
    col = client[args.mongo_db]["ketqua"]

    migrated = skipped = 0
    for doc in col.find():
        ngaychot = doc.get("ngaychot")
        if not ngaychot or not doc.get("kq0"):
            continue
        if draw_repo.has_mb_draw(ngaychot):
            skipped += 1
            continue
        numbers = [doc.get(f"kq{i}", "") or "" for i in range(27)]
        if draw_repo.upsert_mb_draw(ngaychot, numbers, source="mongo-migrate"):
            migrated += 1

    draw_repo.refresh_loto_view()
    logger.info("Migrated=%d skipped=%d total_pg=%s", migrated, skipped, draw_repo.mb_date_range())


if __name__ == "__main__":
    main()
