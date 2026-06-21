from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.prediction.constants import DEFAULT_TOP, MODEL_ENSEMBLE, TARGET_LOTO
from app.prediction.service import compute_next, evaluate, run_backtest_job
from app.prediction.weights import get_tuning_summary

router = APIRouter(prefix="/predictions", tags=["predictions"])


class BacktestRequest(BaseModel):
    from_date: str = Field(..., examples=["2020-01-01"])
    to_date: str = Field(..., examples=["2025-12-31"])
    target: str = TARGET_LOTO
    top_k: int = 20
    models: Optional[List[str]] = None


@router.get("/weights")
def predictions_weights():
    return get_tuning_summary()


@router.get("/next")
def predictions_next(
    target: str = Query(default=TARGET_LOTO),
    top: Optional[int] = Query(default=None),
    model: str = Query(default=MODEL_ENSEMBLE),
    as_of: Optional[str] = Query(default=None),
    persist: bool = Query(default=True),
):
    try:
        return compute_next(target_type=target, top=top, model=model, as_of=as_of, persist=persist)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/backtest")
def predictions_backtest(body: BacktestRequest):
    try:
        return run_backtest_job(
            from_date=body.from_date,
            to_date=body.to_date,
            target=body.target,
            top_k=body.top_k,
            models=body.models,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/evaluate")
def predictions_evaluate(
    date: str = Query(..., description="Draw date to evaluate (yyyy-MM-dd)"),
    target: str = Query(default=TARGET_LOTO),
    top: Optional[int] = Query(default=None),
    model: str = Query(default=MODEL_ENSEMBLE),
):
    try:
        return evaluate(draw_date=date, target_type=target, top=top, model=model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
