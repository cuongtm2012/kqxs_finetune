"""Prediction orchestration service."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import List, Optional, Tuple

from app.prediction.backtest import run_backtest
from app.prediction.constants import (
    DEFAULT_TOP,
    DISCLAIMER,
    MODEL_ENSEMBLE,
    TARGET_TYPES,
)
from app.prediction.ensemble import models_for_target, predict_top, score_ensemble
from app.prediction.features import (
    FeatureContext,
    actual_values_for_date,
    clear_feature_cache,
    latest_draw_date,
    previous_draw_date,
)
from app.repositories.prediction_repo import prediction_repo

logger = logging.getLogger(__name__)


def _resolve_dates(as_of: Optional[str]) -> Tuple[date, date]:
    if as_of:
        as_of_date = date.fromisoformat(as_of)
    else:
        as_of_date = latest_draw_date()
        if as_of_date is None:
            raise ValueError("No draw data in database")
    target_date = as_of_date + timedelta(days=1)
    return as_of_date, target_date


def compute_next(
    target_type: str = "loto",
    top: Optional[int] = None,
    model: str = MODEL_ENSEMBLE,
    as_of: Optional[str] = None,
    persist: bool = True,
) -> dict:
    if target_type not in TARGET_TYPES:
        raise ValueError(f"Invalid target: {target_type}")

    top = top or DEFAULT_TOP.get(target_type, 20)
    as_of_date, target_date = _resolve_dates(as_of)
    ctx = FeatureContext.load(as_of_date, target_type, target_date, use_cache=True)

    if model == "all":
        payload = {
            "target_date": target_date.isoformat(),
            "as_of_date": as_of_date.isoformat(),
            "target_type": target_type,
            "disclaimer": DISCLAIMER,
            "models": {},
            "meta": {"train_days": ctx.train_days},
        }
        for name in models_for_target(target_type) + [MODEL_ENSEMBLE]:
            ranked = predict_top(ctx, name, top)
            payload["models"][name] = [
                {"rank": i + 1, "value": v, "score": round(s, 6)} for i, (v, s) in enumerate(ranked)
            ]
            if persist:
                prediction_repo.save_run(
                    target_date.isoformat(),
                    as_of_date.isoformat(),
                    target_type,
                    name,
                    {},
                    ranked,
                )
        return payload

    ranked = predict_top(ctx, model, top)
    if persist:
        prediction_repo.save_run(
            target_date.isoformat(),
            as_of_date.isoformat(),
            target_type,
            model,
            {},
            ranked,
        )

    combined_models = models_for_target(target_type)
    if model == MODEL_ENSEMBLE:
        _, combined_models = score_ensemble(ctx)

    return {
        "target_date": target_date.isoformat(),
        "as_of_date": as_of_date.isoformat(),
        "target_type": target_type,
        "model": model,
        "disclaimer": DISCLAIMER,
        "predictions": [
            {"rank": i + 1, "value": v, "score": round(s, 6)} for i, (v, s) in enumerate(ranked)
        ],
        "meta": {
            "train_days": ctx.train_days,
            "models_combined": combined_models if model == MODEL_ENSEMBLE else [model],
        },
    }


def evaluate(
    draw_date: str,
    target_type: str = "loto",
    top: Optional[int] = None,
    model: str = MODEL_ENSEMBLE,
) -> dict:
    if target_type not in TARGET_TYPES:
        raise ValueError(f"Invalid target: {target_type}")

    top = top or DEFAULT_TOP.get(target_type, 20)
    target = date.fromisoformat(draw_date)
    as_of_date = previous_draw_date(target)
    if as_of_date is None:
        raise ValueError("No training data before " + draw_date)

    ctx = FeatureContext.load(as_of_date, target_type, target, use_cache=False)
    ranked = predict_top(ctx, model, top)
    predicted = [v for v, _ in ranked]
    actual = sorted(actual_values_for_date(target, target_type))
    pred_set = set(predicted)
    actual_set = set(actual)
    hits = sorted(pred_set & actual_set)
    misses = sorted(pred_set - actual_set)

    return {
        "date": draw_date,
        "target_type": target_type,
        "model": model,
        "top": top,
        "predicted": [{"rank": i + 1, "value": v, "score": round(s, 6)} for i, (v, s) in enumerate(ranked)],
        "actual": actual,
        "hits": hits,
        "misses": misses,
        "hit": len(hits) > 0 if target_type != "de" else (actual[0] in pred_set if actual else False),
        "recall": len(hits) / len(actual_set) if actual_set else 0.0,
    }


def run_backtest_job(
    from_date: str,
    to_date: str,
    target: str = "loto",
    top_k: int = 20,
    models: Optional[List[str]] = None,
) -> dict:
    clear_feature_cache()
    return run_backtest(
        date.fromisoformat(from_date),
        date.fromisoformat(to_date),
        target_type=target,
        top_k=top_k,
        models=models,
    )
