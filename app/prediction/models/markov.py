from typing import Dict, Set

from app.prediction.constants import TARGET_LOTO
from app.prediction.features import FeatureContext


def _present_on_day(day, target_type: str) -> Set[str]:
    if target_type == TARGET_LOTO:
        return day.loto_set
    if target_type == "de":
        return {day.de} if day.de else set()
    if target_type == "dau":
        return set(day.dau_digits)
    if target_type == "dit":
        return set(day.dit_digits)
    return set()


def score_markov(ctx: FeatureContext) -> Dict[str, float]:
    n11: Dict[str, int] = {v: 0 for v in ctx.universe}
    n10: Dict[str, int] = {v: 0 for v in ctx.universe}
    n01: Dict[str, int] = {v: 0 for v in ctx.universe}
    n00: Dict[str, int] = {v: 0 for v in ctx.universe}

    for i in range(len(ctx.days) - 1):
        prev = _present_on_day(ctx.days[i], ctx.target_type)
        nxt = _present_on_day(ctx.days[i + 1], ctx.target_type)
        for value in ctx.universe:
            if value in prev:
                if value in nxt:
                    n11[value] += 1
                else:
                    n10[value] += 1
            else:
                if value in nxt:
                    n01[value] += 1
                else:
                    n00[value] += 1

    last = ctx.last_day
    last_present = _present_on_day(last, ctx.target_type) if last else set()
    scores: Dict[str, float] = {}
    for value in ctx.universe:
        if value in last_present:
            denom = n11[value] + n10[value]
            scores[value] = n11[value] / denom if denom else 0.5
        else:
            denom = n01[value] + n00[value]
            scores[value] = n01[value] / denom if denom else 0.5
    return scores
