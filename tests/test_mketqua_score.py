"""Tests for mketqua XSMB parser and draw-day scoring."""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.expert_score_service import _before_cutoff, draw_cutoff_iso
from app.services.mketqua_service import parse_mketqua_mb

SAMPLE_HTML = """
Xổ số Truyền Thống Thứ năm ngày 02-07-2026
<div id="rs_0_0" rs_len="5">51139</div>
<div id="rs_1_0" rs_len="5">53733</div>
<div id="rs_2_0" rs_len="5">86448</div>
<div id="rs_2_1" rs_len="5">48515</div>
<div id="rs_3_0" rs_len="5">07052</div>
<div id="rs_3_1" rs_len="5">19022</div>
<div id="rs_3_2" rs_len="5">53831</div>
<div id="rs_3_3" rs_len="5">65638</div>
<div id="rs_3_4" rs_len="5">24025</div>
<div id="rs_3_5" rs_len="5">05951</div>
<div id="rs_4_0" rs_len="4">3115</div>
<div id="rs_4_1" rs_len="4">9949</div>
<div id="rs_4_2" rs_len="4">8111</div>
<div id="rs_4_3" rs_len="4">1689</div>
<div id="rs_5_0" rs_len="4">4973</div>
<div id="rs_5_1" rs_len="4">7396</div>
<div id="rs_5_2" rs_len="4">1950</div>
<div id="rs_5_3" rs_len="4">2740</div>
<div id="rs_5_4" rs_len="4">1419</div>
<div id="rs_5_5" rs_len="4">5208</div>
<div id="rs_6_0" rs_len="3">559</div>
<div id="rs_6_1" rs_len="3">824</div>
<div id="rs_6_2" rs_len="3">270</div>
<div id="rs_7_0" rs_len="2">59</div>
<div id="rs_7_1" rs_len="2">78</div>
<div id="rs_7_2" rs_len="2">33</div>
<div id="rs_7_3" rs_len="2">70</div>
"""


def test_parse_mketqua_mb_extracts_27_numbers():
    numbers, station, draw_date = parse_mketqua_mb(SAMPLE_HTML, expected_day="2026-07-02")
    assert len(numbers) == 27
    assert numbers[0] == "51139"
    assert numbers[1] == "53733"
    assert station == "Truyền Thống"
    assert draw_date == "2026-07-02"


def test_draw_cutoff_iso():
    iso = draw_cutoff_iso("2026-07-02")
    assert "+07:00" in iso
    assert "18:00:00" in iso


def test_before_cutoff_rejects_after_18h():
    tz = ZoneInfo("Asia/Ho_Chi_Minh")
    late = datetime(2026, 7, 2, 18, 5, 0, tzinfo=tz).isoformat()
    early = datetime(2026, 7, 2, 17, 30, 0, tzinfo=tz).isoformat()
    assert _before_cutoff(early, "2026-07-02") is True
    assert _before_cutoff(late, "2026-07-02") is False
