from app.services.forum_crawl_service import extract_btd, extract_btd_dau, extract_de_info, parse_picks


def test_btd_de_dac_biet():
    raw = "1/7 : Đề đặc biệt : b02,12 ( n2 - em dự nuôi 7n ) Đề đầu đặc biệt : b34"
    assert extract_btd(raw) == ["02", "12"]
    assert extract_btd_dau(raw) == ["3", "4"]


def test_de_dau_comma_list():
    raw = "Ngày 1/7 đề đầu 0,1,5,6,8 gút lắc"
    de = extract_de_info(raw)
    assert de["dau"] == ["0", "1", "5", "6", "8"]


def test_parse_picks_includes_btd():
    raw = "Đề đặc biệt : b02,12 Đề đầu đặc biệt : b34"
    picks = parse_picks(raw)
    assert picks["btd"] == ["02", "12"]
    assert picks["btd_dau"] == ["3", "4"]
