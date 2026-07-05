"""Multi-day event post parsing (e.g. DaiLoan STL event)."""
from app.services.forum_crawl_service import extract_btl, extract_stl, latest_day_section, parse_picks

DAILOAN_EVENT = """Tham gia Event STL xsmb
Ngày 04/7 BTL 56 miss
STL 37,73 húp 37,73

Ngày 05/7 BTL 78
STL: 48,84"""


def test_latest_day_section_ngay_short_slash():
    scoped = latest_day_section(DAILOAN_EVENT)
    assert scoped.lower().startswith("ngày 05/7")
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
