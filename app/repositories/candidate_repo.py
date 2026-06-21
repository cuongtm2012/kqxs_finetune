import json
from typing import Optional

from app.db import fetch_all, fetch_one, get_conn


class CandidateRepository:
    def save_snapshot(self, payload: dict) -> int:
        with get_conn() as conn:
            row = conn.execute(
                """
                INSERT INTO candidate_snapshots (
                    target_date, as_of_date, target, top, min_filters, sort, payload
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (target_date, target, top, min_filters, sort)
                DO UPDATE SET
                    as_of_date = EXCLUDED.as_of_date,
                    payload = EXCLUDED.payload,
                    created_at = now()
                RETURNING id
                """,
                (
                    payload["target_date"],
                    payload["as_of_date"],
                    payload["target"],
                    payload["top"],
                    payload["min_filters"],
                    payload["sort"],
                    json.dumps(payload, ensure_ascii=False),
                ),
            ).fetchone()
            conn.commit()
        return row["id"]

    def get_snapshot(
        self,
        target_date: str,
        target: str,
        top: int,
        min_filters: int,
        sort: str,
    ) -> Optional[dict]:
        row = fetch_one(
            """
            SELECT id, target_date::text, as_of_date::text, target, top, min_filters, sort,
                   payload, created_at
            FROM candidate_snapshots
            WHERE target_date = %s AND target = %s AND top = %s
              AND min_filters = %s AND sort = %s
            """,
            (target_date, target, top, min_filters, sort),
        )
        if not row:
            return None
        return {
            "id": row["id"],
            "target_date": row["target_date"],
            "as_of_date": row["as_of_date"],
            "target": row["target"],
            "top": row["top"],
            "min_filters": row["min_filters"],
            "sort": row["sort"],
            "payload": row["payload"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }

    def list_snapshots(
        self,
        limit: int = 30,
        target: Optional[str] = None,
        target_date: Optional[str] = None,
    ) -> list[dict]:
        clauses = ["1=1"]
        params: list = []
        if target:
            clauses.append("target = %s")
            params.append(target)
        if target_date:
            clauses.append("target_date = %s")
            params.append(target_date)
        params.append(limit)
        rows = fetch_all(
            f"""
            SELECT id, target_date::text, as_of_date::text, target, top, min_filters, sort,
                   created_at,
                   jsonb_array_length(payload->'candidates') AS candidate_count
            FROM candidate_snapshots
            WHERE {' AND '.join(clauses)}
            ORDER BY target_date DESC, target
            LIMIT %s
            """,
            tuple(params),
        )
        return [
            {
                "id": row["id"],
                "target_date": row["target_date"],
                "as_of_date": row["as_of_date"],
                "target": row["target"],
                "top": row["top"],
                "min_filters": row["min_filters"],
                "sort": row["sort"],
                "candidate_count": row["candidate_count"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            }
            for row in rows
        ]


candidate_repo = CandidateRepository()
