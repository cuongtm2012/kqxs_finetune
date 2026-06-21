import json
from typing import List, Tuple

from app.db import execute, fetch_all, fetch_one, get_conn


class PredictionRepository:
    def save_run(
        self,
        target_date: str,
        as_of_date: str,
        target_type: str,
        model_name: str,
        params: dict,
        items: List[Tuple[str, float]],
    ) -> int:
        with get_conn() as conn:
            row = conn.execute(
                """
                INSERT INTO prediction_runs (target_date, as_of_date, target_type, model_name, params)
                VALUES (%s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (target_date, target_type, model_name)
                DO UPDATE SET
                    as_of_date = EXCLUDED.as_of_date,
                    params = EXCLUDED.params,
                    created_at = now()
                RETURNING id
                """,
                (target_date, as_of_date, target_type, model_name, json.dumps(params)),
            ).fetchone()
            run_id = row["id"]
            conn.execute("DELETE FROM prediction_items WHERE run_id = %s", (run_id,))
            for rank, (value, score) in enumerate(items, start=1):
                conn.execute(
                    """
                    INSERT INTO prediction_items (run_id, rank, value, score)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (run_id, rank, value, score),
                )
            conn.commit()
        return run_id

    def get_run(self, target_date: str, target_type: str, model_name: str) -> dict:
        run = fetch_one(
            """
            SELECT id, target_date::text, as_of_date::text, target_type, model_name, params, created_at
            FROM prediction_runs
            WHERE target_date = %s AND target_type = %s AND model_name = %s
            """,
            (target_date, target_type, model_name),
        )
        if not run:
            return {}
        items = fetch_all(
            """
            SELECT rank, value, score
            FROM prediction_items
            WHERE run_id = %s
            ORDER BY rank
            """,
            (run["id"],),
        )
        run["predictions"] = items
        return run


prediction_repo = PredictionRepository()
