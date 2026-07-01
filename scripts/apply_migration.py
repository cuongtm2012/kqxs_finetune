"""Apply SQL migration files."""

import sys
from pathlib import Path

from app.db import get_conn, init_pool

ROOT = Path(__file__).resolve().parents[1]


def apply(path: str) -> None:
    sql = (ROOT / path).read_text(encoding="utf-8")
    init_pool(min_size=1, max_size=1)
    with get_conn() as conn:
        conn.execute(sql)
        conn.commit()
    print(f"Applied {path}")


if __name__ == "__main__":
    apply(sys.argv[1] if len(sys.argv) > 1 else "db/migrations/004_forum_intelligence.sql")
