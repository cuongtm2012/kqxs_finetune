import logging
from datetime import datetime

from app.db import execute, get_conn
from app.repositories.draw_repo import draw_repo

logger = logging.getLogger(__name__)


class RbkRepository:
    def insert_chot_kq(self, items: list[dict], date: str) -> None:
        with get_conn() as conn:
            for item in items:
                conn.execute(
                    "DELETE FROM chot_predictions WHERE draw_date = %s AND email = %s",
                    (date, item.get("email", "")),
                )
                conn.execute(
                    """
                    INSERT INTO chot_predictions (
                        draw_date, email, name, lo, lodau, lodit, lobt,
                        dedau, dedit, debt, rank,
                        ratio_de, ratio_lo, ratio_lobt, ratio_debt
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        date,
                        item.get("email", ""),
                        item.get("name", ""),
                        item.get("lo", []),
                        item.get("lodau", []),
                        item.get("lodit", []),
                        item.get("lobt", ""),
                        item.get("dedau", []),
                        item.get("dedit", []),
                        item.get("debt", ""),
                        item.get("rank", 0),
                        item.get("ratio_de", ""),
                        item.get("ratio_lo", ""),
                        item.get("ratio_lobt", ""),
                        item.get("debt", ""),
                    ),
                )
            conn.commit()

    def insert_ket_qua(self, kq: dict) -> None:
        numbers = [kq.get(f"kq{i}", "") for i in range(27)]
        draw_repo.upsert_mb_draw(kq["ngaychot"], numbers, source="rbk")

    def insert_cau_dep(self, cd: dict) -> None:
        import json

        draw_date = cd["ngaychot"]
        execute(
            """
            INSERT INTO caudep_snapshots (draw_date, data)
            VALUES (%s, %s::jsonb)
            ON CONFLICT (draw_date) DO UPDATE SET data = EXCLUDED.data
            """,
            (draw_date, json.dumps(cd)),
        )

    def delete_trend(self, date: str) -> None:
        execute("DELETE FROM trends WHERE draw_date = %s", (date,))

    def insert_trend(self, trend: dict) -> None:
        execute(
            "INSERT INTO trends (draw_date, lotto) VALUES (%s, %s) ON CONFLICT (draw_date) DO UPDATE SET lotto = EXCLUDED.lotto",
            (trend["ngaychot"], trend["lotto"]),
        )

    def insert_ket_qua_mn(self, lotto: list[dict], ngaychot: str, draw_date: str) -> None:
        for sub in lotto:
            numbers = [sub.get(f"kq{i}", "") for i in range(18)]
            draw_repo.upsert_regional_draw(
                draw_date=draw_date,
                region="MN",
                station=sub.get("location", ""),
                label=ngaychot,
                numbers=numbers,
                source="rss",
            )

    def insert_ket_qua_mt(self, lotto: list[dict], ngaychot: str, draw_date: str) -> None:
        for sub in lotto:
            numbers = [sub.get(f"kq{i}", "") for i in range(18)]
            draw_repo.upsert_regional_draw(
                draw_date=draw_date,
                region="MT",
                station=sub.get("location", ""),
                label=ngaychot,
                numbers=numbers,
                source="rss",
            )


rbk_repo = RbkRepository()
