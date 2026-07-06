"""Chăn nuôi BTL K3N — mỗi Lần là 1 số + khung ngày, không gộp 4 số."""

from app.services.forum_crawl_service import (
    extract_btl,
    extract_btl_for_target_date,
    parse_picks,
)

NHCSXH = """CHĂN NUÔI BTL K3N THÁNG 7/2026
Lần 1: BTL 36 ( TỪ 01>03/7) Nhận 36n1
Lần 2: BTL 16 ( TỪ 02>04/7) Nhận xịt
Lần 3: BTL 90 ( TỪ 05>07/7) Nhận 90n1
Lần 4: BTL 19 ( TỪ 06>08/7) Nhận"""

QTV1 = """CHĂN NUÔI BTL K3N THÁNG 07/2026
L01: BTL 61 (01-03) nhận N1.
L02: BTL 22 (02-04) nhận N1.
L05: BTL 29 (06-08)"""


def test_legacy_extract_btl_still_single_line():
    assert extract_btl("BTL: 05") == ["05"]


def test_nhcsxh_not_four_numbers_without_target_date():
    """Without target_date, legacy path may still parse — but with target_date fixed."""
    assert parse_picks(NHCSXH, target_date="2026-07-06")["btl"] == ["19"]


def test_nhcsxh_html_entities_from_extension():
    encoded = NHCSXH.replace(">", "&gt;")
    assert parse_picks(encoded, target_date="2026-07-06")["btl"] == ["19"]
    assert parse_picks(encoded, target_date="2026-07-05")["btl"] == ["90"]


def test_nhcsxh_lan_per_day():
    assert extract_btl_for_target_date(NHCSXH, "2026-07-01") == ["36"]
    assert extract_btl_for_target_date(NHCSXH, "2026-07-02") == ["16"]
    assert extract_btl_for_target_date(NHCSXH, "2026-07-03") == ["16"]
    assert extract_btl_for_target_date(NHCSXH, "2026-07-04") == ["16"]
    assert extract_btl_for_target_date(NHCSXH, "2026-07-05") == ["90"]
    assert extract_btl_for_target_date(NHCSXH, "2026-07-06") == ["19"]
    assert extract_btl_for_target_date(NHCSXH, "2026-07-07") == ["19"]
    assert extract_btl_for_target_date(NHCSXH, "2026-07-08") == ["19"]


def test_overlap_prefers_higher_lan():
    # 05/7 in both Lần 3 (05-07) and only Lần 3 for end day 5
    assert extract_btl_for_target_date(NHCSXH, "2026-07-05") == ["90"]
    # 06/7: Lần 3 (05-07) and Lần 4 (06-08) → Lần 4 wins
    assert extract_btl_for_target_date(NHCSXH, "2026-07-06") == ["19"]


def test_qtv1_l_prefix_format():
    assert extract_btl_for_target_date(QTV1, "2026-07-06") == ["29"]


def test_daily_btl_not_lan_format():
    assert extract_btl_for_target_date("BTL 87 chúc ae mm", "2026-07-06") is None
