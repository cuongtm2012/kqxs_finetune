from typing import Dict

from app.prediction.constants import TARGET_LOTO
from app.prediction.features import FeatureContext


def score_frequency(ctx: FeatureContext, window_days: int = None) -> Dict[str, float]:
    days = ctx.days
    if window_days and days:
        cutoff = ctx.as_of_date.toordinal() - window_days
        days = [d for d in days if d.draw_date.toordinal() >= cutoff]

    opp = 0
    counts: Dict[str, int] = {v: 0 for v in ctx.universe}
    for day in days:
        if ctx.target_type == TARGET_LOTO:
            opp += 27
            for loto, cnt in day.loto_hits.items():
                if loto in counts:
                    counts[loto] += cnt
        elif ctx.target_type == "de":
            opp += 1
            counts[day.de] = counts.get(day.de, 0) + 1
        elif ctx.target_type == "dau":
            opp += len(day.dau_digits)
            for d in day.dau_digits:
                counts[d] = counts.get(d, 0) + 1
        elif ctx.target_type == "dit":
            opp += len(day.dit_digits)
            for d in day.dit_digits:
                counts[d] = counts.get(d, 0) + 1

    if opp == 0:
        return {v: 0.0 for v in ctx.universe}
    return {v: counts.get(v, 0) / opp for v in ctx.universe}
