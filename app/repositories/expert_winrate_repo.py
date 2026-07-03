from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from app.db import fetch_all, fetch_one, get_conn


class ExpertWinrateRepository:
    def upsert_win_rate(
        self,
        username: str,
        pick_type: str,
        period_label: str,
        period_start: date,
        period_end: date,
        hits: int,
        total: int,
        win_rate: float,
    ) -> None:
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO expert_win_rates (
                    username, pick_type, period_label, period_start, period_end,
                    hits, total, win_rate, computed_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (username, pick_type, period_label) DO UPDATE SET
                    period_start = EXCLUDED.period_start,
                    period_end = EXCLUDED.period_end,
                    hits = EXCLUDED.hits,
                    total = EXCLUDED.total,
                    win_rate = EXCLUDED.win_rate,
                    computed_at = now()
                """,
                (username, pick_type, period_label, period_start, period_end, hits, total, win_rate),
            )
            conn.commit()

    def replace_pick_results(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        dates = {r["target_date"] for r in rows}
        with get_conn() as conn:
            for d in dates:
                conn.execute(
                    "DELETE FROM expert_pick_results WHERE target_date = %s",
                    (d,),
                )
            for r in rows:
                conn.execute(
                    """
                    INSERT INTO expert_pick_results (
                        target_date, username, pick_type, numbers, hit, draw_de, evaluated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, now())
                    ON CONFLICT (target_date, username, pick_type) DO UPDATE SET
                        numbers = EXCLUDED.numbers,
                        hit = EXCLUDED.hit,
                        draw_de = EXCLUDED.draw_de,
                        evaluated_at = now()
                    """,
                    (
                        r["target_date"],
                        r["username"],
                        r["pick_type"],
                        r["numbers"],
                        r["hit"],
                        r.get("draw_de"),
                    ),
                )
            conn.commit()
        return len(rows)

    def get_pick_results(self, target_date: str) -> list[dict[str, Any]]:
        rows = fetch_all(
            """
            SELECT target_date::text AS target_date, username, pick_type,
                   numbers, hit, draw_de, evaluated_at
            FROM expert_pick_results
            WHERE target_date = %s
            ORDER BY hit DESC, username, pick_type
            """,
            (target_date,),
        )
        return [
            {
                "username": r["username"],
                "pick_type": r["pick_type"],
                "numbers": list(r["numbers"] or []),
                "hit": bool(r["hit"]),
                "draw_de": r["draw_de"],
                "evaluated_at": r["evaluated_at"].isoformat() if r["evaluated_at"] else None,
            }
            for r in rows
        ]

    def get_performance(
        self, username: str, pick_type: str, period_label: str
    ) -> Optional[dict[str, Any]]:
        row = fetch_one(
            """
            SELECT hits, total, win_rate::float AS win_rate, computed_at
            FROM expert_win_rates
            WHERE username = %s AND pick_type = %s AND period_label = %s
            """,
            (username, pick_type, period_label),
        )
        if not row or not row["total"]:
            return None
        rate = float(row["win_rate"])
        return {
            "hits": int(row["hits"]),
            "total": int(row["total"]),
            "rate_pct": round(rate * 100, 1),
            "win_rate": rate,
            "computed_at": row["computed_at"].isoformat() if row["computed_at"] else None,
        }

    def get_period_snapshot(self, period_label: str) -> dict[str, Any]:
        rows = fetch_all(
            """
            SELECT username, pick_type, hits, total, win_rate::float AS win_rate,
                   period_start::text, period_end::text, computed_at
            FROM expert_win_rates
            WHERE period_label = %s
            ORDER BY win_rate DESC, total DESC, username
            """,
            (period_label,),
        )
        users: dict[str, dict] = {}
        period_start = None
        period_end = None
        computed_at = None
        for r in rows:
            period_start = period_start or r["period_start"]
            period_end = period_end or r["period_end"]
            if r["computed_at"] and (computed_at is None or r["computed_at"] > computed_at):
                computed_at = r["computed_at"]
            bucket = users.setdefault(r["username"], {})
            rate = float(r["win_rate"])
            bucket[r["pick_type"]] = {
                "hits": int(r["hits"]),
                "total": int(r["total"]),
                "win_rate": round(rate, 4),
                "rate_pct": round(rate * 100, 1),
            }
        return {
            "period_label": period_label,
            "period_start": period_start,
            "period_end": period_end,
            "computed_at": computed_at.isoformat() if computed_at else None,
            "users": users,
            "row_count": len(rows),
        }


expert_winrate_repo = ExpertWinrateRepository()
