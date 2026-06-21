from typing import Dict

from app.prediction.constants import WEEKDAY_MIN_SAMPLES
from app.prediction.features import FeatureContext
from app.prediction.models.frequency import score_frequency


def score_weekday(ctx: FeatureContext, min_samples: int = WEEKDAY_MIN_SAMPLES) -> Dict[str, float]:
    weekday = ctx.target_date.weekday()
    counts, opp = ctx.weekday_hit_counts(weekday)
    if opp < min_samples:
        return score_frequency(ctx)
    return {v: counts.get(v, 0) / opp for v in ctx.universe}
