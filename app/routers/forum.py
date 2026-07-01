from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.repositories.forum_repo import forum_repo
from app.services.expert_backtest_service import run_backtest, suggest_weights, write_suggested_weights
from app.services.expert_scorer import _load_weights, live_experts
from app.services.expert_winrate_service import get_period_performance, refresh_period
from app.services.forum_ingest_service import ingest_collect_session
from app.services.forum_recommendation_service import build_recommendations

router = APIRouter(prefix="/forum", tags=["forum"])


@router.post("/picks")
def post_forum_picks(body: dict):
    try:
        return ingest_collect_session(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/picks/{target_date}")
def get_forum_picks(target_date: str):
    session = forum_repo.get_session(target_date)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    return session


@router.get("/experts/live")
def get_live_experts(target_date: Optional[str] = Query(None)):
    d = target_date or date.today().isoformat()
    picks = forum_repo.get_user_picks(d)
    if not picks and not forum_repo.get_session(d):
        raise HTTPException(status_code=404, detail="no forum data for date")
    return {
        "target_date": d,
        "experts": live_experts(picks),
        "count": len(picks),
    }


@router.get("/recommendations")
def get_recommendations(target_date: Optional[str] = Query(None)):
    d = target_date or date.today().isoformat()
    return build_recommendations(d)


@router.get("/experts/weights")
def get_expert_weights():
    return {"weights": _load_weights()}


@router.get("/experts/backtest")
def get_expert_backtest(days: int = Query(90, ge=7, le=365)):
    rolling = get_period_performance("rolling_90d")
    if rolling.get("row_count", 0) > 0:
        return {
            "days": days,
            "source": "db",
            "period_label": "rolling_90d",
            "users": rolling["users"],
            "dates_with_draw": rolling.get("row_count"),
        }
    return run_backtest(days)


@router.get("/experts/performance")
def get_expert_performance(period: str = Query("2026-06")):
    return get_period_performance(period)


@router.post("/experts/performance/refresh")
def refresh_expert_performance(
    period: str = Query("2026-06"),
    write_pick_results: bool = Query(False),
    dry_run: bool = Query(False),
):
    return refresh_period(period, write_pick_results=write_pick_results, dry_run=dry_run)


@router.post("/experts/weights/refresh")
def refresh_expert_weights(
    days: int = Query(90, ge=7, le=365),
    blend: float = Query(0.35, ge=0.0, le=1.0),
    dry_run: bool = Query(True),
):
    if dry_run:
        return {
            "dry_run": True,
            "days": days,
            "blend": blend,
            "suggested": suggest_weights(days=days, blend=blend),
            "backtest": run_backtest(days),
        }
    return write_suggested_weights(days=days, blend=blend)
