"""Bayesian sequential update model.

Unlike bayesian_beta.py which uses a static Beta-Binomial conjugate prior,
this model performs FULL Bayesian updating across time:

1. Prior = Beta(alpha_0, beta_0) from overall historical frequency
2. For each time window (short/medium/long), compute posterior
3. Combine windows weighted by recency

This detects numbers that have RECENTLY diverged from their historical baseline.
A number that's been hot in the last 30 days but cold historically will score high.

Key insight: XSMB has 27 prizes per draw, so each draw day provides 27 "trials"
per number. We update the posterior after each draw day.

Formula:
  P(p | data) = Beta(alpha + hits, beta + (trials - hits))
  Expected p = (alpha + hits) / (alpha + beta + trials)
  Score = posterior_mean / prior_mean (lift over prior)
"""
import math
from datetime import timedelta
from typing import Dict, List

from app.prediction.constants import (
    BAYESIAN_UPDATE_ALPHA,
    BAYESIAN_UPDATE_BETA,
    BAYESIAN_UPDATE_WINDOWS,
)
from app.prediction.features import FeatureContext
from app.prediction.models.base import normalize_minmax


def _prior_from_history(ctx: FeatureContext) -> Dict[str, float]:
    """Compute prior probability from full history."""
    hits = ctx.hit_counts()
    total_opp = ctx.total_opportunities
    if total_opp == 0:
        return {v: 1.0 / len(ctx.universe) for v in ctx.universe}
    return {v: hits.get(v, 0) / total_opp for v in ctx.universe}


def _posterior_for_window(
    ctx: FeatureContext,
    window_days: int,
    alpha_prior: float,
    beta_prior: float,
) -> Dict[str, float]:
    """Compute posterior mean for each number in a recent window.

    Treats each draw day as a binomial trial: for each number, the number
    of hits vs misses across 27 slots per day.

    Returns posterior expected probability for each number.
    """
    cutoff = ctx.as_of_date - timedelta(days=window_days)

    window_hits: Dict[str, int] = {v: 0 for v in ctx.universe}
    window_opp: int = 0

    for day in ctx.days:
        if day.draw_date <= cutoff:
            continue
        if ctx.target_type == "loto":
            window_opp += 27
            for loto, cnt in day.loto_hits.items():
                window_hits[loto] = window_hits.get(loto, 0) + cnt
        elif ctx.target_type == "de":
            window_opp += 1
            window_hits[day.de] = window_hits.get(day.de, 0) + 1
        elif ctx.target_type in ("dau", "dit"):
            digits = day.dau_digits if ctx.target_type == "dau" else day.dit_digits
            window_opp += len(digits)
            for d in digits:
                window_hits[d] = window_hits.get(d, 0) + 1

    if window_opp < 10:
        return {}

    posterior: Dict[str, float] = {}
    for v in ctx.universe:
        h = window_hits.get(v, 0)
        trials = window_opp
        alpha_post = alpha_prior + h
        beta_post = beta_prior + (trials - h)
        posterior_mean = alpha_post / (alpha_post + beta_post)
        posterior[v] = posterior_mean

    return posterior


def score_bayesian_update(
    ctx: FeatureContext,
    alpha: float = BAYESIAN_UPDATE_ALPHA,
    beta: float = BAYESIAN_UPDATE_BETA,
    windows: List[int] = None,
) -> Dict[str, float]:
    """Score numbers using Bayesian sequential update across multiple windows.

    For each window, computes the lift of posterior mean over historical prior.
    Combines windows with recency weighting.

    Returns scores in [0, 1] range.
    """
    if windows is None:
        windows = BAYESIAN_UPDATE_WINDOWS

    prior = _prior_from_history(ctx)
    if not prior or max(prior.values()) == 0:
        return {v: 1.0 / len(ctx.universe) for v in ctx.universe}

    window_lifts: List[Dict[str, float]] = []
    window_weights: List[float] = []

    for i, w_days in enumerate(windows):
        posterior = _posterior_for_window(ctx, w_days, alpha, beta)
        if not posterior:
            continue
        lifts = {}
        for v in ctx.universe:
            p = prior.get(v, 1e-6)
            post = posterior.get(v, p)
            lifts[v] = max(post / p, 0.0)
        window_lifts.append(lifts)
        window_weights.append(1.0 / (i + 1))

    if not window_lifts:
        return {v: 0.5 for v in ctx.universe}

    total_w = sum(window_weights)
    combined: Dict[str, float] = {v: 0.0 for v in ctx.universe}
    for lifts, w in zip(window_lifts, window_weights):
        for v in ctx.universe:
            combined[v] += w * lifts.get(v, 1.0)

    if total_w > 0:
        combined = {v: s / total_w for v, s in combined.items()}

    raw: Dict[str, float] = {}
    for v in ctx.universe:
        lift = combined.get(v, 1.0)
        raw[v] = 1.0 / (1.0 + math.exp(-math.log(max(lift, 0.01)) * 2.0))

    return normalize_minmax(raw)
