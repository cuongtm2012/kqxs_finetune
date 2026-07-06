"""Multi-day event post parsing (e.g. DaiLoan STL event)."""
from app.services.forum_crawl_service import (
    day_section_for_target_date,
    extract_btl,
    extract_stl,
    latest_day_section,
    parse_picks,
)

DAILOAN_EVENT = """Tham gia Event STL xsmb
Ngày 04/7 BTL 56 miss
STL 37,73 húp 37,73

Ngày 05/7 BTL 78
STL: 48,84"""

NAAGASAKII = (
    "1/7 Btl 36 Stl: 59,95 Nhận 36**, 59* Đề 40s Xịt "
    "2/7 Btl: 07 Stl: 37,73 Nhận 73* Đề 40s Nhận 39 "
    "3/7 Btl: 45 Stl: 35,53 Nhận 53* Đề 40s Nhận 65 "
    "4/7 Btl: 63 Stl: 08,80 Nhận 08** Đề 40s Nhận 87 "
    "5/7 Btl: 73 Stl; 18,81 Nhận 81* Đề 40s Xịt "
    "6/7 Btl: 40 Stl: 24,42 Đề 40s "
    "01,04,09,10,14,16,17,23,27,32,"
)


def test_latest_day_section_ngay_short_slash():
    scoped = latest_day_section(DAILOAN_EVENT)
    assert scoped.lower().startswith(("ngày 05/7", "05/7"))
    assert "56" not in scoped


def test_dailoan_event_picks_only_latest_day():
    picks = parse_picks(DAILOAN_EVENT)
    assert picks.get("stl") == ["48", "84"]
    assert picks.get("btl") == ["78"]


def test_extract_btl_last_line_only():
    text = "Ngày 05/7 BTL 78\nSTL: 48,84"
    assert extract_btl(text) == ["78"]


def test_extract_stl_last_pair():
    assert extract_stl(DAILOAN_EVENT) == ["48", "84"]


def test_naagasakii_oneline_btl_per_day():
    """One-line cumulative TL post — BTL must match target day only."""
    assert parse_picks(NAAGASAKII, target_date="2026-07-06")["btl"] == ["40"]
    assert parse_picks(NAAGASAKII, target_date="2026-07-06")["stl"] == ["24", "42"]
    assert parse_picks(NAAGASAKII, target_date="2026-07-04")["btl"] == ["63"]
    assert parse_picks(NAAGASAKII, target_date="2026-07-04")["stl"] == ["08", "80"]
    assert parse_picks(NAAGASAKII, target_date="2026-07-02")["btl"] == ["07"]


def test_day_section_for_target_date_inline():
    sec = day_section_for_target_date(NAAGASAKII, "2026-07-06")
    assert sec is not None
    assert sec.startswith("6/7")
    assert "Btl: 40" in sec
    assert "1/7" not in sec


CAPHAO = """Dự đoán xsmb 05/7/2026
BTL:49
STL:43,31 nhận 31*
Dự đoán xsmb 06/7/2026
BTL:55
STL:52,75
Dàn đề 40 số:
00,04,05,08,14,15,23,24,
25,32,33,36,37,38,39,40,
41,42,45,46,48,50,51,52,
54,55,59,63,64,68,69,73,
80,83,84,86,88,93,95,96"""


def test_caphaomamtom_du_doan_multiday():
    p06 = parse_picks(CAPHAO, target_date="2026-07-06")
    assert p06["btl"] == ["55"]
    assert p06["stl"] == ["52", "75"]
    assert p06["dan_pick_type"] == "dan_40s"
    assert len(p06["dan_de"]) == 40
    assert "06" not in p06["dan_de"]
    p05 = parse_picks(CAPHAO, target_date="2026-07-05")
    assert p05["btl"] == ["49"]
    assert p05["stl"] == ["43", "31"]
    assert "dan_de" not in p05
