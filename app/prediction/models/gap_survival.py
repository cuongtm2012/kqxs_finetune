from typing import Dict, Optional

from app.prediction.constants import TARGET_LOTO
from app.prediction.features import FeatureContext


def score_gap(ctx: FeatureContext) -> Dict[str, float]:
    last_seen = ctx.last_seen()
    max_gap = 0
    gaps: Dict[str, int] = {}
    for value in ctx.universe:
        seen = last_seen.get(value)
        if seen is None:
            gap = (ctx.as_of_date - ctx.days[0].draw_date).days + 1 if ctx.days else 0
        else:
            gap = (ctx.as_of_date - seen).days
        gaps[value] = gap
        max_gap = max(max_gap, gap)

    if max_gap == 0:
        return {v: 0.0 for v in ctx.universe}
    return {v: gaps[v] / max_gap for v in ctx.universe}
