from typing import Dict

from app.prediction.constants import EWMA_LAMBDA, TARGET_LOTO
from app.prediction.features import FeatureContext


def score_ewma(ctx: FeatureContext, lam: float = EWMA_LAMBDA) -> Dict[str, float]:
    weighted: Dict[str, float] = {v: 0.0 for v in ctx.universe}
    total_w = 0.0

    for day in ctx.days:
        days_ago = (ctx.as_of_date - day.draw_date).days
        w = lam ** days_ago
        total_w += w
        if ctx.target_type == TARGET_LOTO:
            for loto, cnt in day.loto_hits.items():
                if loto in weighted:
                    weighted[loto] += w * cnt
        elif ctx.target_type == "de":
            weighted[day.de] = weighted.get(day.de, 0.0) + w
        elif ctx.target_type == "dau":
            for d in day.dau_digits:
                weighted[d] = weighted.get(d, 0.0) + w
        elif ctx.target_type == "dit":
            for d in day.dit_digits:
                weighted[d] = weighted.get(d, 0.0) + w

    if total_w == 0:
        return {v: 0.0 for v in ctx.universe}
    denom = sum(weighted.values())
    if denom == 0:
        return {v: 0.0 for v in ctx.universe}
    return {v: weighted[v] / denom for v in ctx.universe}
