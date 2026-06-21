import logging
import re
from typing import Optional

from app.caudep_fields import caudep_field_name
from app.db import execute, fetch_all, fetch_one
from app.repositories.draw_repo import draw_repo
from app.utils.validator import validate_string

logger = logging.getLogger(__name__)


class KqxsRepository:
    def get_chot_kq(
        self, ngaychot: str, email: str, name: str, skip: int, limit: int
    ) -> list[dict]:
        clauses = ["1=1"]
        params: list = []
        if validate_string(ngaychot):
            clauses.append("draw_date = %s")
            params.append(ngaychot)
        if validate_string(email):
            clauses.append("email = %s")
            params.append(email)
        if validate_string(name):
            clauses.append("name ILIKE %s")
            params.append(f"%{name}%")

        params.extend([limit, skip])
        rows = fetch_all(
            f"""
            SELECT lo, lodau, lodit, lobt, dedau, dedit, debt, email, name, rank,
                   ratio_de, ratio_lo, ratio_lobt, ratio_debt,
                   to_char(imported_at, 'HH24:MI:SS') AS time
            FROM chot_predictions
            WHERE {' AND '.join(clauses)}
            ORDER BY id DESC
            LIMIT %s OFFSET %s
            """,
            tuple(params),
        )
        return [dict(row) for row in rows]

    def get_ket_qua(self, ngaychot: str, skip: int, limit: int) -> list[dict]:
        if validate_string(ngaychot):
            item = draw_repo.get_mb_ketqua(ngaychot)
            return [item] if item else []
        return draw_repo.list_mb_ketqua(skip, limit)

    def get_trending(self, ngaychot: str) -> dict:
        if validate_string(ngaychot):
            row = fetch_one("SELECT lotto, draw_date::text FROM trends WHERE draw_date = %s", (ngaychot,))
        else:
            row = fetch_one("SELECT lotto, draw_date::text FROM trends ORDER BY draw_date DESC LIMIT 1")
        if not row:
            return {"lotto": ""}
        return {"lotto": row["lotto"], "ngaychot": row["draw_date"]}

    def get_caudep(self, ngaychot: str, limit: int, nhay: int, lon: int) -> dict:
        row = None
        if validate_string(ngaychot):
            row = fetch_one("SELECT data FROM caudep_snapshots WHERE draw_date = %s", (ngaychot,))
        field = caudep_field_name(limit, nhay, lon)
        value = ""
        if row and row.get("data"):
            value = str(row["data"].get(field, ""))
        return {"caudep": value, "ngaychot": ngaychot}

    def get_ket_qua_mn(self, ngaychot: str) -> dict:
        return self._get_regional("MN", ngaychot)

    def get_ket_qua_mt(self, ngaychot: str) -> dict:
        return self._get_regional("MT", ngaychot)

    def _get_regional(self, region: str, ngaychot: str) -> dict:
        if validate_string(ngaychot):
            draws = fetch_all(
                """
                SELECT id, label, station, draw_date::text
                FROM draws
                WHERE region = %s AND label ILIKE %s
                ORDER BY station
                """,
                (region, f"%{ngaychot}%"),
            )
        else:
            draws = fetch_all(
                """
                SELECT id, label, station, draw_date::text
                FROM draws
                WHERE region = %s
                ORDER BY draw_date DESC, station
                LIMIT 20
                """,
                (region,),
            )
        if not draws:
            return {"ngaychot": "", "lotto": []}

        label = draws[0]["label"] or ""
        lotto = []
        for draw in draws:
            prizes = fetch_all(
                "SELECT slot_index, number FROM prizes WHERE draw_id = %s ORDER BY slot_index",
                (draw["id"],),
            )
            item = {f"kq{i}": "" for i in range(18)}
            for p in prizes:
                if p["slot_index"] < 18:
                    item[f"kq{p['slot_index']}"] = p["number"]
            item["location"] = draw["station"] or ""
            item["ngaychot"] = draw["label"] or draw["draw_date"]
            lotto.append(item)
        return {"ngaychot": label, "lotto": lotto}


kqxs_repo = KqxsRepository()
