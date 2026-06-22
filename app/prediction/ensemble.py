"""Ensemble combiner (M8)."""

from typing import Dict, List, Optional, Tuple

from app.prediction.constants import (
    DEFAULT_ENSEMBLE_WEIGHTS,
    LOTO_DE_MODELS,
    MODEL_BAYESIAN,
    MODEL_BAYESIAN_UPDATE,
    MODEL_CHI_SQUARE,
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
    bayesian_update,
    chi_square,
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
    MODEL_CHI_SQUARE: lambda ctx: chi_square.score_chi_square(ctx),
    MODEL_BAYESIAN_UPDATE: lambda ctx: bayesian_update.score_bayesian_update(ctx),
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


def _cycle_boost(ctx: FeatureContext, scores: Dict[str, float]) -> Dict[str, float]:
    """Boost scores based on lottery cycle patterns.
    
    After backtest 22/06/2026, discovered:
      - Cham trùng với đề hôm trước (de 83→36: cham 3 xuyên 2 kỳ) → boost 5%
      - Số có tổng chữ số = bóng dương của đề hôm trước → boost 10%
      - Bóng dương: 0→5, 1→6, 2→7, 3→8, 4→9, 5→0, 6→1, 7→2, 8→3, 9→4
    """
    last_day = ctx.last_day
    if last_day is None or ctx.target_type not in ("loto", "de"):
        return scores
    
    prev_de = last_day.de  # đề kỳ trước (2 chữ số)
    if not prev_de or len(prev_de) != 2:
        return scores
    
    prev_last_digit = prev_de[-1]  # đuôi đề kỳ trước (cham trùng)
    BONG_DUONG = {"0": "5", "1": "6", "2": "7", "3": "8", "4": "9",
                  "5": "0", "6": "1", "7": "2", "8": "3", "9": "4"}
    
    prev_sum = str((int(prev_de[0]) + int(prev_de[1])) % 10)
    bong_sum = BONG_DUONG.get(prev_sum, prev_sum)
    prev_reverse = prev_de[1] + prev_de[0]  # số đảo XY → YX
    
    boosted = dict(scores)
    for val in boosted:
        if len(val) != 2:
            continue
        # Boost 5% nếu số có cham trùng đuôi đề hôm trước (52.5% pattern)
        if val[-1] == prev_last_digit or val[0] == prev_last_digit:
            boosted[val] *= 1.05
        # Boost 10% nếu tổng 2 số = bóng dương tổng đề hôm trước
        val_sum = str((int(val[0]) + int(val[1])) % 10)
        if val_sum == bong_sum:
            boosted[val] *= 1.10
        # Boost 5% cho số đảo của đề hôm trước (27.1% pattern, loto only)
        if ctx.target_type == "loto" and val == prev_reverse:
            boosted[val] *= 1.05
    
    return boosted


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
    
    # Post-processing: cycle boost
    combined = _cycle_boost(ctx, combined)
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
