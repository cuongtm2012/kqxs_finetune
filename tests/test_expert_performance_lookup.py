from unittest.mock import patch

from app.services.expert_scorer import expert_performance


@patch("app.services.expert_winrate_service.expert_winrate_repo.get_performance")
def test_expert_performance_falls_back_to_dan_40s(mock_get):
    mock_get.side_effect = lambda user, pt, period: (
        {"hits": 17, "total": 18, "rate_pct": 94.4, "win_rate": 0.944}
        if pt == "dan_40s"
        else None
    )
    perf = expert_performance("himle79", "dan_de")
    assert perf is not None
    assert perf["hits"] == 17
    assert perf["total"] == 18
    assert perf["rate_pct"] == 94.4


@patch("app.services.expert_winrate_service.expert_winrate_repo.get_performance", return_value=None)
@patch("app.services.expert_scorer._backtest_users_snapshot")
def test_expert_performance_backtest_dan_family(mock_bt, _mock_db):
    mock_bt.return_value = {
        "himle79": {
            "dan_40s": {"hits": 1, "total": 2, "rate": 0.5},
        },
    }
    perf = expert_performance("himle79", "dan_de", "rolling_90d")
    assert perf == {"hits": 1, "total": 2, "rate_pct": 50.0, "low_sample": True}


@patch("app.services.expert_winrate_service.expert_winrate_repo.get_performance")
def test_expert_performance_low_sample_flag(mock_get):
    mock_get.return_value = {"hits": 2, "total": 2, "rate_pct": 100.0, "win_rate": 1.0}
    perf = expert_performance("nhcsxh", "btl")
    assert perf is not None
    assert perf.get("low_sample") is True


@patch("app.services.expert_winrate_service.expert_winrate_repo.get_performance")
def test_expert_performance_prefers_exact_dan_type(mock_get):
    """dan_40s row must not be replaced by higher-total dan_de sibling."""
    def _lookup(user, pt, period):
        rows = {
            "dan_40s": {"hits": 0, "total": 1, "rate_pct": 0.0, "win_rate": 0.0},
            "dan_de": {"hits": 0, "total": 2, "rate_pct": 0.0, "win_rate": 0.0},
        }
        return rows.get(pt)

    mock_get.side_effect = _lookup
    perf = expert_performance("T98", "dan_40s")
    assert perf == {"hits": 0, "total": 1, "rate_pct": 0.0, "low_sample": True}


@patch("app.services.expert_winrate_service.expert_winrate_repo.get_performance", return_value=None)
@patch("app.services.expert_scorer._backtest_users_snapshot")
def test_expert_performance_no_backtest_for_calendar_period(mock_bt, _mock_db):
    mock_bt.return_value = {
        "Qtv1": {"btl": {"hits": 3, "total": 3, "rate": 1.0}},
    }
    perf = expert_performance("Qtv1", "btl", "2026-06")
    assert perf is None
