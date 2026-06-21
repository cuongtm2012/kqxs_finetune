from app.services.intersection_service import _resolve_picks


def test_intersection_picks_primary_strategy():
    cf = [{"loto": "10", "lift": 5.0}, {"loto": "45", "lift": 4.2}]
    rbk = ["10", "01", "45"]
    counts = {"10": 6, "01": 4, "45": 5}
    intersection = ["10", "45"]

    lotos, used = _resolve_picks(
        strategy="intersection",
        fallback="none",
        intersection=intersection,
        cf_candidates=cf,
        rbk_candidates=rbk,
        rbk_counts=counts,
        top=20,
    )
    assert used == "intersection"
    assert set(lotos) == {"10", "45"}


def test_intersection_fallback_cf_only():
    cf = [{"loto": "10", "lift": 5.0}]
    rbk = ["01"]
    counts = {"01": 6}

    lotos, used = _resolve_picks(
        strategy="intersection",
        fallback="cf_only",
        intersection=[],
        cf_candidates=cf,
        rbk_candidates=rbk,
        rbk_counts=counts,
        top=20,
    )
    assert used == "cf_only"
    assert lotos == ["10"]


def test_intersection_skip_when_no_signal():
    lotos, used = _resolve_picks(
        strategy="intersection",
        fallback="none",
        intersection=[],
        cf_candidates=[],
        rbk_candidates=["01"],
        rbk_counts={"01": 6},
        top=20,
    )
    assert used == "none"
    assert lotos == []
