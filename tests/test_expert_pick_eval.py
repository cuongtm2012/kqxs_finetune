from app.services.expert_pick_eval import (
    dedupe_day_picks,
    evaluate_picks_by_date,
    performance_pick_type_candidates,
)


def test_dedupe_day_picks_keeps_latest_post():
    day = [
        {"username": "a", "pick_type": "btl", "numbers": ["01"], "posted_at": "2026-07-01T10:00:00Z"},
        {"username": "a", "pick_type": "btl", "numbers": ["02"], "posted_at": "2026-07-01T15:00:00Z"},
    ]
    out = dedupe_day_picks(day)
    assert len(out) == 1
    assert out[0]["numbers"] == ["02"]


def test_dedupe_day_picks_canonical_alias():
    day = [
        {"username": "LOKHATA 1789", "pick_type": "btl", "numbers": ["05"], "posted_at": "t1"},
        {"username": "nhcsxh", "pick_type": "btl", "numbers": ["16"], "posted_at": "t2"},
    ]
    out = dedupe_day_picks(day)
    assert len(out) == 1
    assert out[0]["username"] == "nhcsxh"
    assert out[0]["numbers"] == ["16"]


def test_performance_pick_type_candidates_dan_de():
    chain = performance_pick_type_candidates("dan_de")
    assert chain[0] == "dan_de"
    assert "dan_40s" in chain
    assert chain[-1] == "default"


def test_evaluate_picks_by_date_counts_hits():
    picks_by_date = {
        "2026-07-02": [
            {"username": "u1", "pick_type": "dan_40s", "numbers": ["39", "40"], "posted_at": "t1"},
        ],
    }

    def draw_lookup(d: str):
        if d == "2026-07-02":
            return {"kq0": "12339", "kqAr": ["39", "40"]}
        return None

    result = evaluate_picks_by_date(picks_by_date, draw_lookup)
    assert result["stats"]["u1"]["dan_40s"] == {"hits": 1, "total": 1}
