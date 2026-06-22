"""Chi-square goodness-of-fit test: detect numbers that deviate from uniform distribution.

The chi-square test compares observed frequencies against expected uniform frequencies.
Numbers with significantly higher observed counts (positive z-contribution) get boosted scores.
Numbers with lower observed counts get penalized.

This detects PHYSICAL BIAS in the ball-drawing machine — if certain balls are slightly
heavier/lighter/worn, they'll show statistically significant deviation from uniform.
"""
import math
from typing import Dict, List, Tuple

from app.prediction.constants import CHI_SQUARE_MIN_SAMPLES
from app.prediction.features import FeatureContext
from app.prediction.models.base import normalize_minmax


def chi_square_test(
    observed: Dict[str, int],
    total_obs: int,
    n_categories: int,
) -> Tuple[float, List[Tuple[str, float, float]]]:
    """Perform chi-square goodness-of-fit test.

    Returns:
        (chi2_stat, [(category, expected, z_contrib), ...])
    where z_contrib = (observed - expected) / sqrt(expected).
    Positive z_contrib = appears more than expected.
    """
    expected_per = total_obs / n_categories
    if expected_per == 0:
        return 0.0, [(k, 0.0, 0.0) for k in observed]

    chi2 = 0.0
    contributions: List[Tuple[str, float, float]] = []
    for cat in sorted(observed.keys()):
        obs = observed.get(cat, 0)
        diff = obs - expected_per
        contrib = (diff ** 2) / expected_per
        chi2 += contrib
        z = diff / math.sqrt(expected_per)  # signed sqrt of contrib
        contributions.append((cat, expected_per, z))

    return chi2, contributions


def score_chi_square(
    ctx: FeatureContext,
    min_samples: int = CHI_SQUARE_MIN_SAMPLES,
) -> Dict[str, float]:
    """Score numbers by chi-square deviation from uniform.

    Numbers that appear significantly MORE than expected get score > 0.5.
    Numbers that appear LESS get score < 0.5.
    """
    hits = ctx.hit_counts()
    n = len(ctx.universe)
    total = sum(hits.values())

    if total < min_samples:
        # Not enough data — return uniform scores
        return {v: 1.0 / n for v in ctx.universe}

    _, contributions = chi_square_test(hits, total, n)

    # Build raw score from z-contributions
    raw: Dict[str, float] = {}
    for cat, expected, z in contributions:
        # Positive z = appears more = higher score
        # z of 0 → 0.5 (neutral), z of 2 → ~0.75, z of 3 → ~0.85
        # Sigmoid-like: score = 1 / (1 + exp(-z/2))
        # At z=0: 0.5, z=2: 0.73, z=3: 0.82, z=-2: 0.27
        score = 1.0 / (1.0 + math.exp(-z / 2.0))
        raw[cat] = score

    # Normalize to [0, 1] range for ensemble compatibility
    return normalize_minmax(raw)
