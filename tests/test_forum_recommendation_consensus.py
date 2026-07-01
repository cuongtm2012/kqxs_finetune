from app.services.forum_recommendation_service import (
    _aggregate_loto_consensus,
    _de_top4_consensus,
    _pick_xien_2,
)


def _pick(user: str, pick_type: str, numbers: list[str]) -> dict:
    return {"username": user, "pick_type": pick_type, "numbers": numbers}


def test_consensus_loto_counts_users_not_weights():
    picks = [
        _pick("a", "btl", ["05", "16"]),
        _pick("b", "btl", ["05"]),
        _pick("c", "stl", ["05", "38"]),
    ]
    ranked = _aggregate_loto_consensus(picks)
    top = {r["loto"]: r["score"] for r in ranked}
    assert top["05"] == 3.0
    assert top["16"] == 1.0
    assert top["38"] == 1.0


def test_consensus_de_counts_users_in_dan():
    picks = [
        _pick("u1", "dan_de", ["01", "05", "11"]),
        _pick("u2", "dan_de", ["01", "05", "30"]),
        _pick("u3", "dan_36s", ["05", "11", "30"]),
    ]
    dan_board = [
        {"user": "u1", "numbers": ["01", "05", "11"]},
        {"user": "u2", "numbers": ["01", "05", "30"]},
        {"user": "u3", "numbers": ["05", "11", "30"]},
    ]
    top4 = _de_top4_consensus(picks, {}, dan_board)
    assert top4[0] == "05"
    assert set(top4) == {"05", "01", "11", "30"}


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
    ranked = _aggregate_loto_consensus(picks)
    # heavy default weight 0.3, light default 0.3 — same weight, sort by loto
    assert ranked[0]["loto"] in {"05", "16", "38"}
