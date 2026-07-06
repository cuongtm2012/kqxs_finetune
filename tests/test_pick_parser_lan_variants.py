"""Chăn nuôi BTL — alternate Lần / khung ngày formats."""

from app.services.forum_crawl_service import extract_btl_for_target_date, parse_picks

CAPHAO = (
    "CHĂN NUÔI BTL K3N THÁNG 07/2026 LẦN 1 : CHĂN BTL 91 K3N ( TỪ 01/07 -> 03/07 ) nhận 91* N1 "
    "LẦN 2 : CHĂN BTL 58 K3N ( TỪ 02/07 -> 04/07 ) nhận"
)

DANV = (
    "CHĂN NUÔI BTL K3N THÁNG 07/2026 LẦN 1 : CHĂN BTL 07 K3N ( TỪ 01/07 -> 03/07 ): Nhận 07 N1 "
    "LẦN 2 : CHĂN BTL 28 K3N ( TỪ 02/07 -> 04/07 ): Xit "
    "LẦN 3 : CHĂN BTL 87 K3N ( TỪ 05/07 -> 07/07 ):"
)

BINHMINH = (
    "CHĂN NUÔI BTL K3N THÁNG 07/2026: Lần 01: BTL 46 (từ 01-> 03) xịt "
    "Lần 02: BTL 83 (từ 04-> 06) nhận 83N1 Lần 03: BTL 95 (từ 05-> 07)"
)

VIPER_K5N = (
    "CHĂN NUÔI XSMB BTL K5N THÁNG 7/2026 - Lần 01 BTL 84 k5 (từ 01/07-05/07)=>nhận 84 N1 "
    "- Lần 02 BTL 95 k5 (từ 02/07-06/07)=>"
)

HAINAM = (
    "CHĂN BTL K5N THÁNG .7../2026 LẦN 1: BTL 27 (TỪ 01-05) NHẬN 27 N4 "
    "LẦN 2: BTL 87 (TỪ 05-09) NHẬN"
)

SOAIKA = (
    "Dự đoán xsmb 26/6/2026 BTL:19 STL:74,00 nhận 00* Dàn đề 42 số: nhận 54 "
    "Dự đoán xsmb 27/6/2026 BTL:74 STL:73,52"
)


def test_caphaomamtom_full_date_range():
    assert extract_btl_for_target_date(CAPHAO, "2026-07-02") == ["58"]
    assert extract_btl_for_target_date(CAPHAO, "2026-07-03") == ["58"]


def test_caphaomamtom_html_entities():
    enc = CAPHAO.replace(">", "&gt;")
    assert parse_picks(enc, target_date="2026-07-02")["btl"] == ["58"]


def test_danv_k3n_three_lan():
    assert extract_btl_for_target_date(DANV, "2026-07-05") == ["87"]


def test_binhminh_arrow_without_month():
    assert extract_btl_for_target_date(BINHMINH, "2026-07-05") == ["95"]
    assert extract_btl_for_target_date(BINHMINH, "2026-07-04") == ["83"]


def test_viper_no_colon_lan():
    assert extract_btl_for_target_date(VIPER_K5N, "2026-07-02") == ["95"]


def test_hainam_k5n_day_only_range():
    assert extract_btl_for_target_date(HAINAM, "2026-07-05") == ["87"]


def test_soai_ka_du_doan_xsmb_per_day():
    assert parse_picks(SOAIKA, target_date="2026-06-26")["btl"] == ["19"]
    assert parse_picks(SOAIKA, target_date="2026-06-27")["btl"] == ["74"]


def test_short_btl_post():
    assert parse_picks("Btl 69 lot 96", target_date="2026-07-02")["btl"] == ["69"]
