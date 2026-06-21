"""Score normalization helpers."""

from typing import Dict, List, Tuple


def normalize_minmax(scores: Dict[str, float]) -> Dict[str, float]:
    if not scores:
        return {}
    values = list(scores.values())
    lo, hi = min(values), max(values)
    if hi == lo:
        n = len(scores)
        return {k: 1.0 / n for k in scores}
    return {k: (v - lo) / (hi - lo) for k, v in scores.items()}


def rank_scores(scores: Dict[str, float], top: int) -> List[Tuple[str, float]]:
    ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    return ranked[:top]
