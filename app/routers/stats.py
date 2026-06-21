from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.candidate_service import (
    build_candidates,
    evaluate_candidates,
    get_candidate_history,
    get_candidate_snapshot,
    persist_candidate_snapshot,
    run_candidates_backtest,
)
from app.services.rbk_crawler import get_rbk_cau, run_rbk_cau_backtest
from app.utils.date_util import spec_weekday_to_python
from app.services.stats_service import (
    get_calendar,
    get_conditional_frequency,
    get_de_dau,
    get_digits,
    get_gap_detail,
    get_gap_hot_cold,
    get_gap_max_cycle,
    get_gap_nhip,
    get_lo_roi,
    get_loto_theo_db,
    get_loto_theo_loto,
    get_max_dan,
    get_pairs,
)

router = APIRouter(prefix="/stats", tags=["stats"])


class CandidatesBacktestRequest(BaseModel):
    days: int = Field(default=90, ge=1, le=365)
    top: Optional[int] = Field(default=None, ge=1, le=100)
    min_filters: int = Field(default=1, ge=1, le=8)
    target: Literal["loto", "de"] = Field(default="loto")


class RbkCauBacktestRequest(BaseModel):
    days: int = Field(default=30, ge=1, le=90)


class CandidatesPersistRequest(BaseModel):
    target_date: Optional[str] = None
    target: Literal["loto", "de", "both"] = Field(default="both")
    top: Optional[int] = Field(default=None, ge=1, le=100)
    min_filters: int = Field(default=1, ge=1, le=8)
    sort: Literal["score", "filters", "loto"] = Field(default="score")


@router.get("/pairs")
def pairs(
    type: Literal["same-day", "lag-1"] = Query(default="same-day"),
    min_lift: float = Query(default=1.05, ge=1.0),
    min_occ: int = Query(default=30, ge=1),
    limit: int = Query(default=50, ge=1, le=500),
    sort: Literal["lift", "count", "prob"] = Query(default="lift"),
    from_date: str = Query(default="2020-01-01"),
    to_date: Optional[str] = Query(default=None),
):
    return get_pairs(
        pair_type=type,
        min_lift=min_lift,
        min_occ=min_occ,
        limit=limit,
        sort=sort,
        from_date=from_date,
        to_date=to_date,
    )


@router.get("/gap/hot-cold")
def gap_hot_cold(
    sort: Literal["gap", "frequency", "pct_of_max"] = Query(default="gap"),
    limit: int = Query(default=30, ge=1, le=100),
    min_gap: int = Query(default=5, ge=0),
):
    return get_gap_hot_cold(sort=sort, limit=limit, min_gap=min_gap)


@router.get("/gap/nhip")
def gap_nhip(
    loto: str = Query(..., min_length=2, max_length=2),
    from_date: Optional[str] = Query(default=None),
    to_date: Optional[str] = Query(default=None),
):
    return get_gap_nhip(loto=loto, from_date=from_date, to_date=to_date)


@router.get("/gap/max-cycle")
def gap_max_cycle(
    limit: int = Query(default=30, ge=1, le=100),
    min_gap: int = Query(default=5, ge=0),
    sort: Literal["pct_of_max", "gap", "max_gap"] = Query(default="pct_of_max"),
):
    return get_gap_max_cycle(limit=limit, min_gap=min_gap, sort=sort)


@router.get("/gap")
def gap_detail(
    loto: str = Query(..., min_length=2, max_length=2),
    window: int = Query(default=0, ge=0),
):
    return get_gap_detail(loto=loto, window=window)


@router.get("/digits/de-dau")
def digits_de_dau():
    return get_de_dau()


@router.get("/digits")
def digits(
    type: Literal["dau", "dit", "both"] = Query(default="both"),
    window: int = Query(default=0, ge=0),
):
    return get_digits(digit_type=type, window=window)


@router.get("/lo-roi")
def lo_roi(
    loto: Optional[str] = Query(default=None, min_length=2, max_length=2),
    de: Optional[str] = Query(default=None, min_length=2, max_length=2),
    window: int = Query(default=3, ge=1, le=30),
    limit: int = Query(default=20, ge=1, le=200),
):
    return get_lo_roi(loto=loto, de=de, window=window, limit=limit)


@router.get("/calendar/loto-theo-db")
def calendar_loto_theo_db(
    de: Optional[str] = Query(default=None, min_length=2, max_length=2),
    limit: int = Query(default=20, ge=1, le=200),
    window: int = Query(default=0, ge=0),
):
    return get_loto_theo_db(de=de, limit=limit, window=window)


@router.get("/calendar/loto-theo-loto")
def calendar_loto_theo_loto(
    loto: Optional[str] = Query(default=None, min_length=2, max_length=2),
    limit: int = Query(default=20, ge=1, le=200),
    window: int = Query(default=0, ge=0),
):
    return get_loto_theo_loto(loto=loto, limit=limit, window=window)


@router.get("/calendar")
def calendar(
    by: Literal["weekday", "dom", "month"] = Query(default="weekday"),
    loto: Optional[str] = Query(default=None, min_length=2, max_length=2),
    window: int = Query(default=0, ge=0),
):
    return get_calendar(by=by, loto=loto, window=window)


@router.get("/conditional-frequency")
def conditional_frequency(
    db_loto: str = Query(..., min_length=2, max_length=2),
    target_weekday: Optional[int] = Query(
        default=None,
        ge=0,
        le=6,
        description="SPEC weekday: 0=Chủ nhật, 1=Thứ hai, ..., 6=Thứ bảy",
    ),
    min_occ: int = Query(default=2, ge=1),
    limit: int = Query(default=30, ge=1, le=100),
    sort: Literal["count", "lift"] = Query(default="count"),
):
    py_weekday = spec_weekday_to_python(target_weekday) if target_weekday is not None else None
    result = get_conditional_frequency(
        db_loto=db_loto,
        target_weekday=py_weekday,
        min_occ=min_occ,
        limit=limit,
        sort=sort,
    )
    if target_weekday is not None:
        result["target_weekday"] = target_weekday
        result["params"]["target_weekday"] = target_weekday
    return result


@router.get("/rbk-cau")
def rbk_cau(
    date: Optional[str] = Query(default=None),
    limit: int = Query(default=5, ge=1, le=9),
    min_cau: int = Query(default=1, ge=1),
):
    return get_rbk_cau(date_str=date, limit=limit, min_cau=min_cau)


@router.get("/candidates")
def candidates(
    target_date: Optional[str] = Query(default=None),
    top: Optional[int] = Query(default=None, ge=1, le=100),
    min_filters: int = Query(default=1, ge=1, le=8),
    sort: Literal["score", "filters", "loto"] = Query(default="score"),
    target: Literal["loto", "de"] = Query(default="loto"),
    include_reasons: bool = Query(default=True),
    include_pair_detail: bool = Query(default=False),
):
    try:
        return build_candidates(
            target_date=target_date,
            top=top,
            min_filters=min_filters,
            sort=sort,
            target=target,
            include_reasons=include_reasons,
            include_pair_detail=include_pair_detail,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/candidates/evaluate")
def candidates_evaluate(
    target_date: str = Query(..., description="Ngày đã có KQXS"),
    target: Literal["loto", "de"] = Query(default="loto"),
    top: Optional[int] = Query(default=None, ge=1, le=100),
    min_filters: int = Query(default=1, ge=1, le=8),
    sort: Literal["score", "filters", "loto"] = Query(default="score"),
):
    try:
        return evaluate_candidates(
            target_date=target_date,
            target=target,
            top=top,
            min_filters=min_filters,
            sort=sort,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/candidates/backtest")
def candidates_backtest(body: CandidatesBacktestRequest):
    return run_candidates_backtest(
        days=body.days,
        top=body.top,
        min_filters=body.min_filters,
        target=body.target,
    )


@router.post("/rbk-cau/backtest")
def rbk_cau_backtest(body: RbkCauBacktestRequest):
    return run_rbk_cau_backtest(days=body.days)


@router.post("/candidates/persist")
def candidates_persist(body: CandidatesPersistRequest):
    targets = [body.target] if body.target != "both" else ["loto", "de"]
    saved: list[dict] = []
    for target in targets:
        try:
            result = build_candidates(
                target_date=body.target_date,
                top=body.top,
                min_filters=body.min_filters,
                sort=body.sort,
                target=target,
            )
            snapshot_id = persist_candidate_snapshot(
                result,
                min_filters=body.min_filters,
                top=body.top,
            )
            saved.append(
                {
                    "id": snapshot_id,
                    "target": target,
                    "target_date": result["target_date"],
                    "candidate_count": len(result["candidates"]),
                }
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"saved": saved}


@router.get("/candidates/history")
def candidates_history(
    limit: int = Query(default=30, ge=1, le=365),
    target: Optional[Literal["loto", "de"]] = Query(default=None),
    target_date: Optional[str] = Query(default=None),
):
    return get_candidate_history(limit=limit, target=target, target_date=target_date)


@router.get("/candidates/snapshot")
def candidates_snapshot(
    target_date: str = Query(...),
    target: Literal["loto", "de"] = Query(default="loto"),
    top: Optional[int] = Query(default=None, ge=1, le=100),
    min_filters: int = Query(default=1, ge=1, le=8),
    sort: Literal["score", "filters", "loto"] = Query(default="score"),
):
    try:
        return get_candidate_snapshot(
            target_date=target_date,
            target=target,
            top=top,
            min_filters=min_filters,
            sort=sort,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/max-dan")
def max_dan(
    size: int = Query(default=3, ge=3, le=5),
    min_co_occur: int = Query(default=20, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    from_date: str = Query(default="2020-01-01"),
    to_date: Optional[str] = Query(default=None),
):
    return get_max_dan(
        size=size,
        min_co_occur=min_co_occur,
        limit=limit,
        from_date=from_date,
        to_date=to_date,
    )
