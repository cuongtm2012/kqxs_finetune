"""Ensemble weight tuning via cached walk-forward scores."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Set, Tuple

from app.prediction.constants import (
    LOTO_DE_MODELS,
    MODEL_DIGIT,
    MODEL_ENSEMBLE,
    TARGET_DAU,
    TARGET_DE,
    TARGET_DIT,
    TARGET_LOTO,
)
from app.prediction.ensemble import MODEL_FNS, models_for_target
from app.prediction.features import (
    FeatureContext,
    actual_values_for_date,
    draw_dates_between,
    load_all_day_records,
)
from app.prediction.models.base import normalize_minmax


@dataclass
class TuningSample:
    target_date: date
    actual: Set[str]
    model_scores: Dict[str, Dict[str, float]] = field(default_factory=dict)


def _build_cache(
    from_date: date,
    to_date: date,
    target_type: str,
    stride: int = 1,
    max_days: Optional[int] = None,
) -> Tuple[List[TuningSample], List[str]]:
    all_days = load_all_day_records()
    day_index = {d.draw_date: i for i, d in enumerate(all_days)}
    model_names = models_for_target(target_type)
    samples: List[TuningSample] = []

    dates = draw_dates_between(from_date, to_date)
    if stride > 1:
        dates = dates[::stride]
    if max_days and len(dates) > max_days:
        step = max(1, len(dates) // max_days)
        dates = dates[::step][:max_days]

    for target_date in dates:
        idx = day_index.get(target_date)
        if idx is None or idx == 0:
            continue
        as_of = all_days[idx - 1].draw_date
        ctx = FeatureContext(
            as_of_date=as_of,
            target_type=target_type,
            target_date=target_date,
            days=all_days[:idx],
        )
        actual = actual_values_for_date(target_date, target_type)
        if not actual:
            continue
        scores = {}
        for name in model_names:
            raw = MODEL_FNS[name](ctx)
            scores[name] = normalize_minmax(raw)
        samples.append(TuningSample(target_date=target_date, actual=actual, model_scores=scores))

    return samples, model_names


def _combine_scores(
    sample: TuningSample,
    model_names: List[str],
    weights: Dict[str, float],
) -> Dict[str, float]:
    universe = next(iter(sample.model_scores.values())).keys()
    combined = {v: 0.0 for v in universe}
    total_w = 0.0
    for name in model_names:
        w = weights.get(name, 0.0)
        if w <= 0:
            continue
        total_w += w
        for v in universe:
            combined[v] += w * sample.model_scores[name].get(v, 0.0)
    if total_w > 0:
        combined = {k: v / total_w for k, v in combined.items()}
    return combined


def _evaluate_weights(
    samples: List[TuningSample],
    model_names: List[str],
    weights: Dict[str, float],
    top_k: int,
    target_type: str,
) -> Dict[str, float]:
    hit_sum = 0.0
    recall_sum = 0.0
    for sample in samples:
        combined = _combine_scores(sample, model_names, weights)
        ranked = sorted(combined.items(), key=lambda x: (-x[1], x[0]))[:top_k]
        predicted = {v for v, _ in ranked}
        actual = sample.actual
        overlap = len(predicted & actual)
        if target_type == TARGET_DE:
            hit_sum += 1.0 if overlap else 0.0
            recall_sum += 1.0 if overlap else 0.0
        else:
            hit_sum += 1.0 if overlap > 0 else 0.0
            recall_sum += overlap / len(actual) if actual else 0.0
    n = len(samples) or 1
    return {
        "hit_rate": hit_sum / n,
        "recall_at_k": recall_sum / n,
        "days": len(samples),
    }


def _weights_from_recall(
    samples: List[TuningSample],
    model_names: List[str],
    top_k: int,
    target_type: str,
) -> Dict[str, float]:
    """Seed: each model alone, weight ∝ its recall."""
    recalls = {}
    for name in model_names:
        solo = {m: 1.0 if m == name else 0.0 for m in model_names}
        recalls[name] = _evaluate_weights(samples, model_names, solo, top_k, target_type)["recall_at_k"]
    floor = 0.01
    total = sum(max(recalls[m], floor) for m in model_names)
    return {m: max(recalls[m], floor) / total for m in model_names}


def tune_weights(
    from_date: date,
    to_date: date,
    target_type: str = TARGET_LOTO,
    top_k: int = 20,
    n_samples: int = 3000,
    seed: int = 42,
    stride: int = 2,
    max_days: Optional[int] = 600,
) -> dict:
    samples, model_names = _build_cache(from_date, to_date, target_type, stride=stride, max_days=max_days)
    if not samples:
        return {"error": "no samples"}

    import sys
    print(
        f"tune {target_type}: {len(samples)} days, {n_samples} search iterations",
        file=sys.stderr,
        flush=True,
    )

    rng = random.Random(seed)
    seed_weights = _weights_from_recall(samples, model_names, top_k, target_type)
    best_weights = dict(seed_weights)
    best = _evaluate_weights(samples, model_names, best_weights, top_k, target_type)

    candidates = [best_weights]
    for _ in range(n_samples):
        if rng.random() < 0.3:
            weights = {m: rng.random() for m in model_names}
        else:
            weights = {m: best_weights[m] * rng.uniform(0.2, 1.8) for m in model_names}
        total = sum(weights.values())
        weights = {m: w / total for m, w in weights.items()}
        candidates.append(weights)

    for weights in candidates:
        metrics = _evaluate_weights(samples, model_names, weights, top_k, target_type)
        if metrics["recall_at_k"] > best["recall_at_k"] + 1e-9:
            best = metrics
            best_weights = weights
        elif abs(metrics["recall_at_k"] - best["recall_at_k"]) < 1e-9 and metrics["hit_rate"] > best["hit_rate"]:
            best = metrics
            best_weights = weights

    solo_metrics = {}
    for name in model_names:
        solo = {m: 1.0 if m == name else 0.0 for m in model_names}
        solo_metrics[name] = _evaluate_weights(samples, model_names, solo, top_k, target_type)

    rounded = {k: round(v, 4) for k, v in best_weights.items()}
    return {
        "target_type": target_type,
        "top_k": top_k,
        "period": {"from": from_date.isoformat(), "to": to_date.isoformat()},
        "weights": rounded,
        "ensemble_metrics": {**best, "recall_at_k": round(best["recall_at_k"], 4), "hit_rate": round(best["hit_rate"], 4)},
        "solo_metrics": {
            k: {"recall_at_k": round(v["recall_at_k"], 4), "hit_rate": round(v["hit_rate"], 4)}
            for k, v in solo_metrics.items()
        },
        "seed_weights": {k: round(v, 4) for k, v in seed_weights.items()},
    }


def tune_all(
    from_date: str = "2020-01-01",
    to_date: str = "2025-12-31",
    n_samples: int = 5000,
    stride: int = 2,
    max_days: Optional[int] = 800,
) -> dict:
    start = date.fromisoformat(from_date)
    end = date.fromisoformat(to_date)
    loto = tune_weights(
        start, end, TARGET_LOTO, top_k=20, n_samples=n_samples, stride=stride, max_days=max_days
    )
    de = tune_weights(
        start, end, TARGET_DE, top_k=10, n_samples=n_samples, stride=stride, max_days=max_days
    )
    dau = tune_weights(
        start, end, TARGET_DAU, top_k=5, n_samples=n_samples // 2, stride=stride, max_days=max_days
    )
    dit = tune_weights(
        start, end, TARGET_DIT, top_k=5, n_samples=n_samples // 2, stride=stride, max_days=max_days
    )
    return {"loto": loto, "de": de, "dau": dau, "dit": dit}
