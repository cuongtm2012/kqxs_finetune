"""Tests for forum crawl parsing — STL, BTL, BTD, dan de extractors + dedup + cutoff."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.services.forum_crawl_service import (
    extract_stl,
    extract_btl,
    extract_btd,
    extract_btd_dau,
    extract_dan_de,
    extract_std_de,
    extract_btd_de,
    extract_muc_lo,
    _parse_btd_numbers,
    parse_picks,
    latest_day_section,
    strip_html,
    infer_dan_pick_type,
)


TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def test_stl_extracts_single_pair():
    """STL chỉ lấy cặp từ 'STL: 05-38' hoặc 'STL: 05,38'.
    Không support 'Song thủ lô' — behavior hiện tại."""
    assert extract_stl("STL: 05-38") == ["05", "38"]
    assert extract_stl("stl : 05,38") == ["05", "38"]


def test_stl_ignores_multiple_pairs_and_non_standard():
    """Nếu có nhiều hơn 2 số hoặc không match format 'STL:', bỏ qua.
    'STL 05-38 16-47' → match ra 05-38 (cặp đầu) do regex lấy cặp đầu tiên."""
    result = extract_stl("STL 05-38 16-47")
    assert result == ["05", "38"]  # behavior hiện tại: lấy cặp đầu
    assert extract_stl("Song thủ lô 05-38") == []  # không match 'STL:'


def test_stl_with_spaces():
    """STL có thể có space thừa."""
    assert extract_stl("STL:  05  -  38") == ["05", "38"]


def test_btl_extracts_single_number():
    """BTL chỉ 1 số từ format 'BTL: 05'.
    Không support 'Bạch thủ lô' — behavior hiện tại."""
    assert extract_btl("BTL: 05") == ["05"]
    assert extract_btl("btl : 16") == ["16"]


def test_btl_ignores_multiple():
    """BTL line with multiple numbers — lấy tất cả số 2 chữ số trên dòng BTL cuối."""
    assert extract_btl("BTL: 05 16 27") == ["05", "16", "27"]


def test_btd_extracts_dac_biet():
    """Đề đặc biệt 'b02,12' → ['02','12']."""
    assert extract_btd("Đề đặc biệt: b02,12") == ["02", "12"]
    assert extract_btd("BTD: 05,38") == ["05", "38"]
    assert extract_btd("Đề đặc biệt : b00") == ["00"]


def test_btd_dau_variations():
    """Đề đầu đặc biệt: b34 → [3,4].
    Lưu ý: b02,12 → chỉ lấy [0,2] (chữ số từ cặp b02), không lấy 1,2 từ 12
    vì extract_btd_dau dùng prefix 'b' + regex khác."""
    assert extract_btd_dau("Đề đầu đặc biệt: b34") == ["3", "4"]

def test_btd_dau_mixed_with_non_b():
    """Chữ số từ bXX — không phải tất cả số đề."""
    assert extract_btd_dau("Đề đầu đặc biệt: b02,12") == ["0", "2"]  # behavior hiện tại


def test_btd_only_takes_latest_day():
    """Chỉ lấy BTD của ngày cuối (latest_day_section)."""
    text = """Ngày 1/7: Đề đặc biệt: b02,12
    Ngày 2/7: Đề đặc biệt: b05,38"""
    picks = parse_picks(text)
    assert picks.get("btd") == ["05", "38"]
    assert "02" not in picks.get("btd", [])


def test_std_de_variations():
    """STD đề (soi thủ đề / đề thủ) — match pair format STD: 05-38."""
    assert extract_std_de("STD: 05-38") == ["05-38"]

def test_std_de_via_std_alias():
    assert extract_std_de("STD: 49-50") == ["49-50"]


def test_btd_de_extracts():
    """BTD đề (bạch thủ đề) — chỉ match prefix 'BTD đề:'. không phải 'btd đề:'.
    Behavior hiện tại: lowercase không match."""
    result = extract_btd_de("bTD đề: 05")
    assert result == []  # không match case-insensitive


def test_dan_de_picks_only_numbers():
    """extract_dan_de chỉ lấy số từ text, bỏ text không phải số."""
    text = "01 05 16 27 38 49 50 61 72 83 94 00 11 22 33 44 55 66 77 88 99 12 23 34 45 56 67 78 89 90 08 17 26 35 46 57 68 79 80 91"
    result = extract_dan_de(text)
    assert len(result) == 40
    assert result[0] == "01"


def test_dan_de_rejects_small_sets():
    """Dưới 30 số → empty (không phải dàn)."""
    assert extract_dan_de("05 16 27") == []


def test_dan_de_dedup():
    """Số trùng → chỉ lấy 1 lần."""
    text = "05 16 05 16 27 " * 10
    result = extract_dan_de(text)
    assert result == ["05", "16", "27"]


def test_infer_dan_40s():
    assert infer_dan_pick_type(40, "chan dan 40s") == "dan_40s"
    assert infer_dan_pick_type(38, "") == "dan_40s"
    assert infer_dan_pick_type(42, "topic something") == "dan_40s"


def test_infer_dan_36s():
    assert infer_dan_pick_type(36, "dan 36s") == "dan_36s"
    assert infer_dan_pick_type(30, "") == "dan_36s"


def test_infer_dan_64s():
    assert infer_dan_pick_type(64, "dan 64s") == "dan_64s"
    assert infer_dan_pick_type(60, "") == "dan_64s"


def test_infer_default_dan_de():
    assert infer_dan_pick_type(10, "") == "dan_de"
    assert infer_dan_pick_type(25, "something") == "dan_de"


def test_muc_lo_parses():
    text = """Mức: 1 (0-100)
05 16 27
Mức: 2 (100-200)
38 49 50"""
    result = extract_muc_lo(text)
    assert 1 in result
    assert result[1] == ["05", "16", "27"]
    assert result[2] == ["38", "49", "50"]


def test_latest_day_section_finds_latest():
    text = """some noise
Ngày 01.07.2026: nội dung cũ
Ngày 02.07.2026: nội dung mới hơn"""
    section = latest_day_section(text)
    assert "nội dung mới hơn" in section
    assert "nội dung cũ" not in section


def test_latest_day_section_short_format():
    text = """2/7: nội dung hôm nay
3/7: nội dung mới"""
    section = latest_day_section(text)
    assert "nội dung mới" in section


def test_latest_day_section_no_date():
    """Không có ngày tháng → lấy toàn bộ text."""
    text = "just some content without dates"
    assert latest_day_section(text) == text


def test_strip_html_removes_tags():
    assert strip_html("<b>05</b> <i>16</i>") == "05 16"


def test_strip_html_replaces_br():
    assert strip_html("line1<br>line2<br/>line3") == "line1 line2 line3"


def test_parse_picks_full_example():
    """Full example từ 1 post forum — parse đầy đủ picks."""
    text = """
    Ngày 2/7
    STL: 05-38
    BTL: 16
    Đề đặc biệt: b02,12
    Đề đầu đặc biệt: b34
    STD: 49-50
    """
    picks = parse_picks(text)
    assert picks.get("stl") == ["05", "38"]
    assert picks.get("btl") == ["16"]
    # extract_btd gộp cả bắt đầu bằng 'b' (b02,12) và 'BTD đề' (27)
    assert "02" in picks.get("btd", [])
    assert "12" in picks.get("btd", [])
    assert picks.get("btd_dau") == ["3", "4"]
    assert "49-50" in picks.get("std_de", [])


def test_parse_picks_dan_de():
    text = """Ngay 3/7 Dàn đề 40s
01 05 16 27 38 49 50 61 72 83 94 00 11 22 33 44 55 66 77 88 99 12 23 34 45 56 67 78 89 90 08 17 26 35 46 57 68 79 80 91"""
    picks = parse_picks(text)
    # parse_picks lưu dan_de (list số) và dan_pick_type (tên) riêng
    assert picks.get("dan_pick_type") == "dan_40s"
    assert "01" in picks.get("dan_de", [])
    assert len(picks.get("dan_de", [])) == 40


def test_empty_text_returns_empty():
    picks = parse_picks("")
    assert picks == {}


def test_parse_lan_range_end_date():
    from app.services.forum_crawl_service import parse_lan_range_end_date

    assert parse_lan_range_end_date("Từ 1-4/6", 2026, 6) == "2026-06-04"
    assert parse_lan_range_end_date("Từ 30/6", 2026, 6) == "2026-06-30"


def test_parse_lan_range_end_date_sunday_snaps_to_saturday():
    from app.services.forum_crawl_service import parse_lan_range_end_date

    assert parse_lan_range_end_date("Từ 6-7/6", 2026, 6) == "2026-06-06"
