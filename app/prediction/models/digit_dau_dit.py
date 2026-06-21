from typing import Dict

from app.prediction.constants import ALL_DIGITS, ALL_LOTOS, TARGET_DAU, TARGET_DIT, TARGET_LOTO
from app.prediction.features import FeatureContext


def _digit_freq(ctx: FeatureContext, kind: str) -> Dict[str, float]:
    counts: Dict[str, int] = {d: 0 for d in ALL_DIGITS}
    total = 0
    for day in ctx.days:
        digits = day.dau_digits if kind == "dau" else day.dit_digits
        total += len(digits)
        for d in digits:
            counts[d] = counts.get(d, 0) + 1
    if total == 0:
        return {d: 0.1 for d in ALL_DIGITS}
    return {d: counts[d] / total for d in ALL_DIGITS}


def score_digit(ctx: FeatureContext) -> Dict[str, float]:
    if ctx.target_type == TARGET_DAU:
        return _digit_freq(ctx, "dau")
    if ctx.target_type == TARGET_DIT:
        return _digit_freq(ctx, "dit")

    dau = _digit_freq(ctx, "dau")
    dit = _digit_freq(ctx, "dit")
    scores: Dict[str, float] = {}
    for loto in ALL_LOTOS:
        a, b = loto[0], loto[1]
        scores[loto] = dau.get(a, 0.0) * dit.get(b, 0.0)
    return scores
