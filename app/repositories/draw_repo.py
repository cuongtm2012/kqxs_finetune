import json
import logging
from typing import Optional

from app.db import execute, fetch_all, fetch_one, get_conn
from app.services.lottery_format import flat_numbers_to_prize_rows, prizes_to_ketqua

logger = logging.getLogger(__name__)


class DrawRepository:
    @staticmethod
    def _validate_mb_numbers(numbers: list[str]) -> bool:
        if len(numbers) != 27:
            logger.warning("MB numbers len=%d != 27, rejecting", len(numbers))
            return False
        for i, n in enumerate(numbers):
            if not isinstance(n, str) or not n:
                logger.warning(
                    "MB numbers[%d]=%r invalid (empty or not string), rejecting", i, n
                )
                return False
        return True

    def upsert_mb_draw(
        self,
        draw_date: str,
        numbers: list[str],
        station: Optional[str] = None,
        source: str = "xskt",
    ) -> bool:
        if not self._validate_mb_numbers(numbers):
            return False
        prize_rows = flat_numbers_to_prize_rows(numbers)
        if not prize_rows:
            return False

        with get_conn() as conn:
            existing = conn.execute(
                "SELECT id FROM draws WHERE region = 'MB' AND draw_date = %s",
                (draw_date,),
            ).fetchone()
            if existing:
                draw_id = existing["id"]
                conn.execute(
                    """
                    UPDATE draws
                    SET station = %s, source = %s, updated_at = now()
                    WHERE id = %s
                    """,
                    (station, source, draw_id),
                )
            else:
                draw_id = conn.execute(
                    """
                    INSERT INTO draws (draw_date, region, station, source)
                    VALUES (%s, 'MB', %s, %s)
                    RETURNING id
                    """,
                    (draw_date, station, source),
                ).fetchone()["id"]

            conn.execute("DELETE FROM prizes WHERE draw_id = %s", (draw_id,))
            for row in prize_rows:
                conn.execute(
                    """
                    INSERT INTO prizes (
                        draw_id, slot_index, prize_level, prize_order,
                        number, last_two, first_digit, last_digit
                    ) VALUES (
                        %(draw_id)s, %(slot_index)s, %(prize_level)s, %(prize_order)s,
                        %(number)s, %(last_two)s, %(first_digit)s, %(last_digit)s
                    )
                    """,
                    {"draw_id": draw_id, **row},
                )
            conn.commit()
        return True

    def upsert_regional_draw(
        self,
        draw_date: str,
        region: str,
        station: str,
        label: str,
        numbers: list[str],
        source: str = "xskt",
    ) -> bool:
        prize_rows = []
        for slot_index, number in enumerate(numbers[:18]):
            if not number:
                continue
            from app.services.lottery_format import split_number_fields

            fields = split_number_fields(number)
            prize_rows.append(
                {
                    "slot_index": slot_index,
                    "prize_level": f"S{slot_index}",
                    "prize_order": 0,
                    **fields,
                }
            )
        if not prize_rows:
            return False

        with get_conn() as conn:
            existing = conn.execute(
                """
                SELECT id FROM draws
                WHERE region = %s AND draw_date = %s AND COALESCE(station, '') = %s
                """,
                (region, draw_date, station or ""),
            ).fetchone()
            if existing:
                draw_id = existing["id"]
                conn.execute(
                    "UPDATE draws SET label = %s, source = %s, updated_at = now() WHERE id = %s",
                    (label, source, draw_id),
                )
            else:
                draw_id = conn.execute(
                    """
                    INSERT INTO draws (draw_date, region, station, label, source)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (draw_date, region, station, label, source),
                ).fetchone()["id"]

            conn.execute("DELETE FROM prizes WHERE draw_id = %s", (draw_id,))
            for row in prize_rows:
                conn.execute(
                    """
                    INSERT INTO prizes (
                        draw_id, slot_index, prize_level, prize_order,
                        number, last_two, first_digit, last_digit
                    ) VALUES (
                        %(draw_id)s, %(slot_index)s, %(prize_level)s, %(prize_order)s,
                        %(number)s, %(last_two)s, %(first_digit)s, %(last_digit)s
                    )
                    """,
                    {"draw_id": draw_id, **row},
                )
            conn.commit()
        return True

    def has_mb_draw(self, draw_date: str) -> bool:
        row = fetch_one(
            """
            SELECT 1 FROM draws d
            JOIN prizes p ON p.draw_id = d.id
            WHERE d.region = 'MB' AND d.draw_date = %s
            LIMIT 1
            """,
            (draw_date,),
        )
        return row is not None

    def get_mb_ketqua(self, draw_date: str) -> Optional[dict]:
        draw = fetch_one(
            "SELECT id, draw_date::text AS draw_date FROM draws WHERE region = 'MB' AND draw_date = %s",
            (draw_date,),
        )
        if not draw:
            return None
        prizes = fetch_all(
            """
            SELECT slot_index, prize_level, prize_order, number, last_two, first_digit, last_digit
            FROM prizes WHERE draw_id = %s ORDER BY slot_index
            """,
            (draw["id"],),
        )
        if not prizes:
            return None
        return prizes_to_ketqua(draw["draw_date"], prizes)

    def list_mb_ketqua(self, skip: int = 0, limit: int = 10) -> list[dict]:
        draws = fetch_all(
            """
            SELECT id, draw_date::text AS draw_date
            FROM draws WHERE region = 'MB'
            ORDER BY draw_date DESC
            OFFSET %s LIMIT %s
            """,
            (skip, limit),
        )
        results = []
        for draw in draws:
            prizes = fetch_all(
                """
                SELECT slot_index, prize_level, prize_order, number, last_two, first_digit, last_digit
                FROM prizes WHERE draw_id = %s ORDER BY slot_index
                """,
                (draw["id"],),
            )
            if prizes:
                results.append(prizes_to_ketqua(draw["draw_date"], prizes))
        return results

    def count_mb_draws(self) -> int:
        row = fetch_one("SELECT COUNT(*)::int AS c FROM draws WHERE region = 'MB'")
        return row["c"] if row else 0

    def mb_date_range(self) -> Optional[dict]:
        return fetch_one(
            """
            SELECT MIN(draw_date)::text AS oldest, MAX(draw_date)::text AS newest,
                   COUNT(*)::int AS total
            FROM draws WHERE region = 'MB'
            """
        )

    def save_checkpoint(self, job_name: str, last_date: str, stats: dict) -> None:
        execute(
            """
            INSERT INTO import_checkpoints (job_name, last_date, stats, updated_at)
            VALUES (%s, %s, %s::jsonb, now())
            ON CONFLICT (job_name) DO UPDATE
            SET last_date = EXCLUDED.last_date, stats = EXCLUDED.stats, updated_at = now()
            """,
            (job_name, last_date, json.dumps(stats)),
        )

    def get_checkpoint(self, job_name: str) -> Optional[dict]:
        return fetch_one("SELECT * FROM import_checkpoints WHERE job_name = %s", (job_name,))

    def cleanup_checkpoints(self, retention_days: int = 90) -> int:
        from datetime import datetime, timedelta, timezone

        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        result = execute(
            "DELETE FROM import_checkpoints WHERE updated_at < %s",
            (cutoff,),
        )
        deleted = result.rowcount if hasattr(result, "rowcount") else 0
        logger.info("Cleaned up %s old import_checkpoints (retention=%s days)", deleted, retention_days)
        return deleted

    def refresh_loto_view(self) -> None:
        execute("SELECT refresh_loto_views()")


draw_repo = DrawRepository()
