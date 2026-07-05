from unittest.mock import patch

from app.services.forum_recommendation_service import (
    ScoringContext,
    _aggregate_loto_scores,
    _best_btl,
    build_recommendations,
    resolve_scoring_context,
)


def test_resolve_scoring_context_invalid():
    try:
        resolve_scoring_context("invalid")
        assert False, "expected ValueError"
    except ValueError as e:
        assert "scoring_mode" in str(e)


@patch("app.services.forum_recommendation_service.forum_repo")
def test_build_recommendations_includes_scoring_metadata(mock_repo):
    mock_repo.get_session.return_value = None
    mock_repo.summary_dict_from_picks.return_value = {"dan_board": []}
    mock_repo.get_user_picks.return_value = [
        {
            "username": "T98",
            "pick_type": "stl",
            "numbers": ["12", "21"],
            "posted_at": "2026-07-04T10:00:00+00:00",
            "forum": "chan_nuoi",
            "post_id": "1",
        },
    ]
    data = build_recommendations("2026-07-05", scoring_mode="blend")
    assert data["scoring_mode"] == "blend"
    assert data["scoring_period"]
    assert data["live_experts"][0]["effective_weight"] is not None


def test_aggregate_loto_weight_vs_blend():
    picks = [
        {
            "username": "nhcsxh",
            "pick_type": "btl",
            "numbers": ["50"],
            "posted_at": "2026-07-04T10:00:00+00:00",
        },
        {
            "username": "lowuser",
            "pick_type": "btl",
            "numbers": ["50"],
            "posted_at": "2026-07-04T11:00:00+00:00",
        },
    ]
    ctx_weight = ScoringContext(mode="weight", period_label="rolling_90d")
    with patch(
        "app.services.forum_recommendation_service.expert_weight",
        side_effect=lambda u, pt: 1.0 if u == "nhcsxh" else 0.3,
    ):
        w_rows = _aggregate_loto_scores(picks, ctx_weight)
    nhcsxh_score_w = next(r for r in w_rows if r["loto"] == "50")["score"]
    assert nhcsxh_score_w == 1.3

    ctx_blend = ScoringContext(mode="blend", period_label="rolling_90d")
    with patch(
        "app.services.forum_recommendation_service.expert_effective_weight",
        side_effect=lambda u, pt, **kw: 0.35 if u == "nhcsxh" else 0.28,
    ):
        b_rows = _aggregate_loto_scores(picks, ctx_blend)
    blend_score = next(r for r in b_rows if r["loto"] == "50")["score"]
    assert blend_score < nhcsxh_score_w


@patch(
    "app.services.forum_recommendation_service.expert_effective_weight",
    side_effect=lambda u, pt, **kw: 0.35 if u == "nhcsxh" else 0.5,
)
def test_best_btl_blend_not_pure_manual(_mock_eff):
    picks = [
        {"username": "nhcsxh", "pick_type": "btl", "numbers": ["10"], "posted_at": "a"},
        {"username": "other", "pick_type": "btl", "numbers": ["22"], "posted_at": "b"},
    ]
    ctx = ScoringContext(mode="blend", period_label="rolling_90d")
    assert _best_btl(picks, ctx) == "22"
