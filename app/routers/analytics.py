from datetime import date, timedelta

from fastapi import APIRouter, Query

from app.db import fetch_all, fetch_one
from app.repositories.draw_repo import draw_repo

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/stats")
def stats():
    mb = draw_repo.mb_date_range() or {}
    prizes = fetch_one(
        """
        SELECT COUNT(*)::int AS total_prizes
        FROM prizes p JOIN draws d ON d.id = p.draw_id
        WHERE d.region = 'MB'
        """
    )
    return {
        "mb_draws": mb.get("total", 0),
        "oldest": mb.get("oldest"),
        "newest": mb.get("newest"),
        "mb_prizes": prizes["total_prizes"] if prizes else 0,
    }


@router.get("/loto-frequency")
def loto_frequency(
    from_date: str = Query(default=""),
    to_date: str = Query(default=""),
    limit: int = Query(default=20, le=100),
):
    clauses = ["d.region = 'MB'"]
    params: list = []
    if from_date:
        clauses.append("d.draw_date >= %s")
        params.append(from_date)
    if to_date:
        clauses.append("d.draw_date <= %s")
        params.append(to_date)
    params.append(limit)
    rows = fetch_all(
        f"""
        SELECT p.last_two AS loto, COUNT(*)::int AS hits
        FROM prizes p
        JOIN draws d ON d.id = p.draw_id
        WHERE {' AND '.join(clauses)}
        GROUP BY p.last_two
        ORDER BY hits DESC, loto
        LIMIT %s
        """,
        tuple(params),
    )
    return rows


@router.get("/loto-gan")
def loto_gan(loto: str = Query(min_length=2, max_length=2)):
    row = fetch_one(
        """
        SELECT MAX(d.draw_date)::text AS last_seen
        FROM prizes p
        JOIN draws d ON d.id = p.draw_id
        WHERE d.region = 'MB' AND p.last_two = %s
        """,
        (loto,),
    )
    if not row or not row.get("last_seen"):
        return {"loto": loto, "last_seen": None, "days_ago": None}

    last = date.fromisoformat(row["last_seen"])
    return {
        "loto": loto,
        "last_seen": row["last_seen"],
        "days_ago": (date.today() - last).days,
    }


@router.post("/refresh-views")
def refresh_views():
    draw_repo.refresh_loto_view()
    return {"status": "ok"}
