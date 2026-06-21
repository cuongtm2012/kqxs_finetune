"""Load tuned ensemble weights from JSON artifact."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict

from app.prediction.constants import (
    DEFAULT_ENSEMBLE_WEIGHTS,
    MODEL_BAYESIAN,
    MODEL_DIGIT,
    MODEL_EWMA,
    MODEL_FREQUENCY,
    MODEL_GAP,
    MODEL_MARKOV,
    MODEL_WEEKDAY,
    TARGET_DAU,
    TARGET_DE,
    TARGET_DIT,
    TARGET_LOTO,
)

_WEIGHTS_PATH = Path(__file__).resolve().parent / "tuned_weights.json"

# Walk-forward tuned 2020-01-01 .. 2025-12-31 (see tuned_weights.json)
ENSEMBLE_WEIGHTS_LOTO = {
    MODEL_FREQUENCY: 0.0716,
    MODEL_EWMA: 0.4468,
    MODEL_GAP: 0.0253,
    MODEL_MARKOV: 0.0711,
    MODEL_BAYESIAN: 0.0864,
    MODEL_WEEKDAY: 0.1465,
    MODEL_DIGIT: 0.1523,
}

ENSEMBLE_WEIGHTS_DE = {
    MODEL_FREQUENCY: 0.1066,
    MODEL_EWMA: 0.2415,
    MODEL_GAP: 0.0406,
    MODEL_MARKOV: 0.307,
    MODEL_BAYESIAN: 0.1712,
    MODEL_WEEKDAY: 0.1333,
}

ENSEMBLE_WEIGHTS_DAU = {
    MODEL_FREQUENCY: 0.1159,
    MODEL_EWMA: 0.2259,
    MODEL_GAP: 0.1689,
    MODEL_MARKOV: 0.2772,
    MODEL_BAYESIAN: 0.0287,
    MODEL_WEEKDAY: 0.1834,
}

ENSEMBLE_WEIGHTS_DIT = {
    MODEL_FREQUENCY: 0.0797,
    MODEL_EWMA: 0.4769,
    MODEL_GAP: 0.1627,
    MODEL_MARKOV: 0.0434,
    MODEL_BAYESIAN: 0.1276,
    MODEL_WEEKDAY: 0.1098,
}

ENSEMBLE_WEIGHTS_BY_TARGET = {
    TARGET_LOTO: ENSEMBLE_WEIGHTS_LOTO,
    TARGET_DE: ENSEMBLE_WEIGHTS_DE,
    TARGET_DAU: ENSEMBLE_WEIGHTS_DAU,
    TARGET_DIT: ENSEMBLE_WEIGHTS_DIT,
}


@lru_cache(maxsize=1)
def _load_json_weights() -> Dict[str, Dict[str, float]]:
    if not _WEIGHTS_PATH.is_file():
        return {}
    data = json.loads(_WEIGHTS_PATH.read_text(encoding="utf-8"))
    out: Dict[str, Dict[str, float]] = {}
    for target, block in data.items():
        weights = block.get("weights")
        if isinstance(weights, dict):
            out[target] = {str(k): float(v) for k, v in weights.items()}
    return out


def ensemble_weights_for(target_type: str) -> Dict[str, float]:
    """Prefer tuned_weights.json; fallback to baked-in constants."""
    json_weights = _load_json_weights()
    if target_type in json_weights:
        return json_weights[target_type]
    return ENSEMBLE_WEIGHTS_BY_TARGET.get(target_type, DEFAULT_ENSEMBLE_WEIGHTS)


def reload_tuned_weights() -> None:
    _load_json_weights.cache_clear()


def get_tuning_summary() -> dict:
    if not _WEIGHTS_PATH.is_file():
        return {"source": "defaults", "targets": {}}
    data = json.loads(_WEIGHTS_PATH.read_text(encoding="utf-8"))
    return {"source": str(_WEIGHTS_PATH.name), "targets": data}
