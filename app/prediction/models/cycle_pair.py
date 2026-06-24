"""Cycle pair model — predicts based on 50 fixed pair cycles.

Each pair (e.g. 38-83) has a stable cycle: the average gap between appearances.
If the current gap >= avg cycle, the pair is DUE — boost both numbers in the pair.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Tuple

from app.prediction.features import FeatureContext
from app.prediction.constants import ALL_LOTOS

# 50 fixed pairs from mketqua.net
FIFTY_PAIRS: List[Tuple[str, str]] = [
    ("00", "55"), ("01", "10"), ("02", "20"), ("03", "30"), ("04", "40"),
    ("05", "50"), ("06", "60"), ("07", "70"), ("08", "80"), ("09", "90"),
    ("11", "66"), ("12", "21"), ("13", "31"), ("14", "41"), ("15", "51"),
    ("16", "61"), ("17", "71"), ("18", "81"), ("19", "91"), ("22", "77"),
    ("23", "32"), ("24", "42"), ("25", "52"), ("26", "62"), ("27", "72"),
    ("28", "82"), ("29", "92"), ("33", "88"), ("34", "43"), ("35", "53"),
    ("36", "63"), ("37", "73"), ("38", "83"), ("39", "93"), ("44", "99"),
    ("45", "54"), ("46", "64"), ("47", "74"), ("48", "84"), ("49", "94"),
    ("56", "65"), ("57", "75"), ("58", "85"), ("59", "95"), ("67", "76"),
    ("68", "86"), ("69", "96"), ("78", "87"), ("79", "97"), ("89", "98"),
]

# Build lookup: num -> [(pair_idx, partner), ...]
NUM_TO_PAIRS: Dict[str, List[Tuple[int, str]]] = {}
for idx, (a, b) in enumerate(FIFTY_PAIRS):
    for num in (a, b):
        NUM_TO_PAIRS.setdefault(num, []).append((idx, b if num == a else a))


def compute_pair_cycles(ctx: FeatureContext) -> Dict[str, float]:
    """Score each loto number based on its pair cycle status.
    
    For each of the 50 pairs, compute:
      - avg_cycle: average gap (days) between appearances in last 30 days
      - current_gap: days since last appearance
      - If current_gap >= avg_cycle → both numbers in pair get boosted
    
    Returns dict {loto_num: score}, where score reflects "cycle due" strength.
    """
    from collections import defaultdict
    
    # Build pair hit timeline
    pair_dates: Dict[int, List[date]] = defaultdict(list)
    
    for day in ctx.days:
        # For each pair, check if any number hit
        for idx, (a, b) in enumerate(FIFTY_PAIRS):
            if a in day.loto_set or b in day.loto_set:
                pair_dates[idx].append(day.draw_date)
    
    # Filter to last 30 days
    cutoff = ctx.as_of_date - timedelta(days=30)
    
    scores: Dict[str, float] = {v: 0.0 for v in ALL_LOTOS}
    
    for idx, (a, b) in enumerate(FIFTY_PAIRS):
        hits = [d for d in pair_dates.get(idx, []) if d >= cutoff]
        
        if len(hits) < 2:
            continue
        
        # Average cycle in last 30 days
        gaps = [(hits[i+1] - hits[i]).days for i in range(len(hits) - 1)]
        avg_cycle = sum(gaps) / len(gaps) if gaps else 0
        
        # Current gap (days since last hit)
        last_hit = hits[-1]
        current_gap = (ctx.as_of_date - last_hit).days
        
        # Penalty for very short cycles (noise)
        if avg_cycle < 1.0:
            continue
        
        # Score: how overdue is this pair?
        # cycle_score = (current_gap - avg_cycle) / avg_cycle
        # Positive means overdue, higher = more due
        if current_gap >= avg_cycle:
            due_ratio = (current_gap - avg_cycle) / avg_cycle
            # Base boost + extra for severity
            boost = 0.15 + min(0.25, due_ratio * 0.15)
            
            # Apply boost to both numbers in the pair
            for num in (a, b):
                scores[num] += boost
    
    return scores


def score_cycle_pair(ctx: FeatureContext) -> Dict[str, float]:
    """Public API — score numbers by pair cycle analysis.
    
    Returns normalized scores for all 100 loto numbers.
    Pair cycles are independent of target_type (same for loto and de).
    """
    from app.prediction.models.base import normalize_minmax
    raw = compute_pair_cycles(ctx)
    return normalize_minmax(raw)
