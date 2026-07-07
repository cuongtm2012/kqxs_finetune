from unittest.mock import patch

from app.services.forum_recommendation_service import (
    ScoringContext,
    _aggregate_loto_consensus,
    _de_top4_anti_consensus,
    _pick_xien_2,
    resolve_scoring_context,
)


def _pick(user: str, pick_type: str, numbers: list[str]) -> dict:
    return {"username": user, "pick_type": pick_type, "numbers": numbers}


def test_consensus_loto_counts_users_not_weights():
    picks = [
        _pick("a", "btl", ["05", "16"]),
        _pick("b", "btl", ["05"]),
        _pick("c", "stl", ["05", "38"]),
    ]
    ctx = resolve_scoring_context("weight")
    ranked = _aggregate_loto_consensus(picks, ctx)
    top = {r["loto"]: r["score"] for r in ranked}
    assert top["05"] == 3.0
    assert top["16"] == 1.0
    assert top["38"] == 1.0


def test_anti_consensus_de_returns_four_numbers():
    picks = [
        {"username": "u1", "pick_type": "btd", "numbers": ["01"], "forum": "thao_luan"},
        {"username": "u2", "pick_type": "btd_de", "numbers": ["05", "11"], "forum": "thao_luan"},
        {"username": "u3", "pick_type": "std_de", "numbers": ["30-31"], "forum": "thao_luan"},
    ]
    ctx = resolve_scoring_context("weight")
    top4 = _de_top4_anti_consensus(picks, {}, [], ctx)
    assert len(top4) == 4
    assert all(len(n) == 2 for n in top4)


def test_pick_xien_from_consensus_rank():
    ranked = [
        {"loto": "05", "score": 3},
        {"loto": "16", "score": 2},
        {"loto": "47", "score": 2},
        {"loto": "59", "score": 1},
        {"loto": "61", "score": 1},
        {"loto": "72", "score": 1},
    ]
    assert _pick_xien_2(ranked) == ["05-16", "47-59", "61-72"]


def test_consensus_tiebreak_prefers_low_weight_at_one_vote():
    picks = [
        _pick("heavy", "btl", ["05", "16"]),
        _pick("light", "stl", ["38"]),
    ]
    ctx = ScoringContext(mode="weight", period_label="rolling_90d")
    with patch(
        "app.services.forum_recommendation_service.expert_weight",
        side_effect=lambda u, pt: 0.9 if u == "heavy" else 0.1,
    ):
        ranked = _aggregate_loto_consensus(picks, ctx)
    # 1 phiếu: số từ cao thủ trọng số thấp (light → 38) xếp trước
    assert ranked[0]["loto"] == "38"
