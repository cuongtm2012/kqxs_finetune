from app.services.expert_pick_eval import performance_pick_type_candidates
from app.services.expert_scorer import _pick_first_backtest_stats, expert_weight


def test_expert_weight_himle79_stl_is_unknown():
    assert expert_weight("himle79", "stl") == 0.3


def test_expert_weight_himle79_dan_40s_uses_dan_de():
    assert expert_weight("himle79", "dan_40s") == 0.94


def test_expert_weight_t98_stl_unchanged():
    assert expert_weight("T98", "stl") == 0.95


def test_expert_weight_nhcsxh_btl_uses_default():
    assert expert_weight("nhcsxh", "btl") == 1.0


def test_backtest_stats_dan_family_uses_first_candidate():
    bucket = {
        "dan_40s": {"hits": 1, "total": 2, "rate": 0.5},
        "dan_36s": {"hits": 3, "total": 3, "rate": 1.0},
    }
    best = _pick_first_backtest_stats(bucket, "dan_de")
    assert best is not None
    assert best["total"] == 2


def test_performance_candidates_include_dan_family():
    chain = performance_pick_type_candidates("dan_40s")
    assert chain[0] == "dan_40s"
    assert "dan_de" in chain
