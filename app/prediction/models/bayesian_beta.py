from typing import Dict

from app.prediction.constants import BAYESIAN_ALPHA, BAYESIAN_BETA
from app.prediction.features import FeatureContext


def score_bayesian(
    ctx: FeatureContext,
    alpha: float = BAYESIAN_ALPHA,
    beta: float = BAYESIAN_BETA,
) -> Dict[str, float]:
    hits = ctx.hit_counts()
    opp = ctx.total_opportunities
    denom = alpha + beta + opp
    if denom == 0:
        return {v: 1.0 / len(ctx.universe) for v in ctx.universe}
    return {v: (alpha + hits.get(v, 0)) / denom for v in ctx.universe}
