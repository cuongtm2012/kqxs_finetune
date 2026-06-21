"""Walk-forward backtest runner."""

import json
import random
from datetime import date
from typing import Dict, List, Optional

from app.db import execute_returning
from app.prediction.constants import MODEL_ENSEMBLE, MODEL_FREQUENCY, TARGET_DE, TARGET_LOTO
from app.prediction.ensemble import predict_top
from app.prediction.features import (
    FeatureContext,
    actual_values_for_date,
    draw_dates_between,
    load_all_day_records,
)


def _random_baseline_loto(top_k: int, trials: int = 10000) -> float:
    hits = 0
    for _ in range(trials):
        picked = set(random.sample(range(100), top_k))
        actual = set(random.sample(range(100), 27))
        if picked & actual:
            hits += 1
    return hits / trials


def _random_baseline_de(top_k: int) -> float:
    return top_k / 100.0


def _evaluate_day(
    predicted: List[str],
    actual: set,
    target_type: str,
) -> Dict[str, float]:
    pred_set = set(predicted)
    if target_type == TARGET_DE:
        hit = 1.0 if actual & pred_set else 0.0
        return {"hit": hit, "recall": hit}
    if not actual:
        return {"hit": 0.0, "recall": 0.0}
    overlap = len(pred_set & actual)
    return {
        "hit": 1.0 if overlap > 0 else 0.0,
        "recall": overlap / len(actual),
    }


def run_backtest(
    from_date: date,
    to_date: date,
    target_type: str = TARGET_LOTO,
    top_k: int = 20,
    models: Optional[List[str]] = None,
    save_report: bool = True,
) -> dict:
    all_days = load_all_day_records()
    if not all_days:
        return {"error": "no data"}

    dates = draw_dates_between(from_date, to_date)
    if not dates:
        return {"error": "no draw dates in range"}

    if models is None:
        models = [MODEL_ENSEMBLE, MODEL_FREQUENCY]

    results: Dict[str, Dict[str, float]] = {
        name: {"hit_sum": 0.0, "recall_sum": 0.0, "days": 0} for name in models
    }

    day_index = {d.draw_date: i for i, d in enumerate(all_days)}

    for target_date in dates:
        idx = day_index.get(target_date)
        if idx is None or idx == 0:
            continue
        as_of = all_days[idx - 1].draw_date
        ctx = FeatureContext.from_days(all_days, as_of, target_type, target_date)
        actual = actual_values_for_date(target_date, target_type)
        if not actual:
            continue

        for model_name in models:
            ranked = predict_top(ctx, model_name, top_k)
            predicted = [v for v, _ in ranked]
            metrics = _evaluate_day(predicted, actual, target_type)
            bucket = results[model_name]
            bucket["hit_sum"] += metrics["hit"]
            bucket["recall_sum"] += metrics["recall"]
            bucket["days"] += 1

    random_base = (
        _random_baseline_de(top_k)
        if target_type == TARGET_DE
        else _random_baseline_loto(top_k)
    )

    model_metrics = {}
    for name, bucket in results.items():
        days = bucket["days"] or 1
        hit_rate = bucket["hit_sum"] / days
        model_metrics[name] = {
            "hit_rate": round(hit_rate, 4),
            "recall_at_k": round(bucket["recall_sum"] / days, 4),
            "lift": round(hit_rate / random_base, 4) if random_base else None,
            "days_evaluated": bucket["days"],
        }

    report = {
        "period": {"from": from_date.isoformat(), "to": to_date.isoformat()},
        "target": target_type,
        "top_k": top_k,
        "models": model_metrics,
        "random_baseline": round(random_base, 4),
    }

    if save_report:
        for name, metrics in model_metrics.items():
            execute_returning(
                """
                INSERT INTO backtest_reports (target_type, model_name, period_from, period_to, top_k, metrics)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                RETURNING id
                """,
                (
                    target_type,
                    name,
                    from_date.isoformat(),
                    to_date.isoformat(),
                    top_k,
                    json.dumps(metrics),
                ),
            )

    return report
