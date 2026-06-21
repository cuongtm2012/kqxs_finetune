"""Ensemble combiner (M8)."""

from typing import Dict, List, Optional, Tuple

from app.prediction.constants import (
    DEFAULT_ENSEMBLE_WEIGHTS,
    LOTO_DE_MODELS,
    MODEL_BAYESIAN,
    MODEL_DIGIT,
    MODEL_ENSEMBLE,
    MODEL_EWMA,
    MODEL_FREQUENCY,
    MODEL_GAP,
    MODEL_MARKOV,
    MODEL_WEEKDAY,
    TARGET_DAU,
    TARGET_DE,
    TARGET_DIT,
    TARGET_LOTO,
)
from app.prediction.weights import ensemble_weights_for
from app.prediction.features import FeatureContext
from app.prediction.models.base import normalize_minmax, rank_scores
from app.prediction.models import (
    bayesian_beta,
    digit_dau_dit,
    ewma,
    frequency,
    gap_survival,
    markov,
    weekday_station,
)

MODEL_FNS = {
    MODEL_FREQUENCY: lambda ctx: frequency.score_frequency(ctx),
    MODEL_EWMA: lambda ctx: ewma.score_ewma(ctx),
    MODEL_GAP: lambda ctx: gap_survival.score_gap(ctx),
    MODEL_MARKOV: lambda ctx: markov.score_markov(ctx),
    MODEL_BAYESIAN: lambda ctx: bayesian_beta.score_bayesian(ctx),
    MODEL_WEEKDAY: lambda ctx: weekday_station.score_weekday(ctx),
    MODEL_DIGIT: lambda ctx: digit_dau_dit.score_digit(ctx),
}


def models_for_target(target_type: str) -> List[str]:
    if target_type in (TARGET_DAU, TARGET_DIT):
        return [MODEL_FREQUENCY, MODEL_EWMA, MODEL_GAP, MODEL_MARKOV, MODEL_BAYESIAN, MODEL_WEEKDAY]
    if target_type == TARGET_DE:
        return list(LOTO_DE_MODELS)
    return list(LOTO_DE_MODELS) + [MODEL_DIGIT]


def score_model(ctx: FeatureContext, model_name: str) -> Dict[str, float]:
    fn = MODEL_FNS.get(model_name)
    if fn is None:
        raise ValueError(f"Unknown model: {model_name}")
    return fn(ctx)


def score_ensemble(
    ctx: FeatureContext,
    weights: Optional[Dict[str, float]] = None,
) -> Tuple[Dict[str, float], List[str]]:
    if weights is None:
        weights = ensemble_weights_for(ctx.target_type)
    active = models_for_target(ctx.target_type)
    combined: Dict[str, float] = {v: 0.0 for v in ctx.universe}
    total_w = 0.0

    for name in active:
        w = weights.get(name, 0.0)
        if w <= 0:
            continue
        raw = score_model(ctx, name)
        norm = normalize_minmax(raw)
        for value in ctx.universe:
            combined[value] += w * norm.get(value, 0.0)
        total_w += w

    if total_w > 0:
        combined = {k: v / total_w for k, v in combined.items()}
    return combined, active


def predict_top(
    ctx: FeatureContext,
    model_name: str,
    top: int,
    weights: Optional[Dict[str, float]] = None,
) -> List[Tuple[str, float]]:
    if model_name == MODEL_ENSEMBLE:
        scores, _ = score_ensemble(ctx, weights)
    else:
        scores = score_model(ctx, model_name)
    return rank_scores(scores, top)
