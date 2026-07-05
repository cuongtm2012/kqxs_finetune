from unittest.mock import patch

from app.services.expert_scorer import (
    BLEND_PRIOR,
    expert_effective_weight,
    expert_weight,
    wilson_lower,
)


def test_wilson_lower_monotonic():
    assert wilson_lower(0, 0) == 0.5
    assert wilson_lower(1, 1) < 0.25
    low = wilson_lower(7, 13)
    high = wilson_lower(17, 18)
    assert 0.28 <= low <= 0.45
    assert high > 0.74
    assert wilson_lower(8, 13) > wilson_lower(7, 13)


def test_effective_weight_mode_weight():
    with patch("app.services.expert_scorer.expert_weight", return_value=0.95):
        assert expert_effective_weight("T98", "stl", mode="weight") == 0.95


@patch("app.services.expert_scorer.expert_performance", return_value=None)
@patch("app.services.expert_scorer.expert_weight", return_value=1.0)
def test_blend_no_perf_gates_manual(mock_w, _mock_perf):
    eff = expert_effective_weight("nhcsxh", "btl", mode="blend")
    assert eff == round(1.0 * BLEND_PRIOR, 3)
    assert eff < 1.0


@patch(
    "app.services.expert_scorer.expert_performance",
    return_value={"hits": 1, "total": 1, "rate_pct": 100.0},
)
@patch("app.services.expert_scorer.expert_weight", return_value=1.0)
def test_blend_low_sample_shrinks(_mock_w, _mock_perf):
    eff = expert_effective_weight("x", "btl", mode="blend")
    assert eff < 1.0


@patch(
    "app.services.expert_scorer.expert_performance",
    return_value={"hits": 7, "total": 13, "rate_pct": 53.8},
)
@patch("app.services.expert_scorer.expert_weight", return_value=0.94)
def test_blend_himle79_dan_below_manual(_mock_w, _mock_perf):
    eff = expert_effective_weight("himle79", "dan_40s", mode="blend")
    assert 0.3 < eff < 0.94


@patch("app.services.expert_scorer.expert_performance", return_value=None)
def test_measured_no_perf_is_unknown(_mock_perf):
    assert expert_effective_weight("nhcsxh", "btl", mode="measured") == 0.3
