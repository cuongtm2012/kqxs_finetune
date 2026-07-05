"""Parser gaps for collect→score pipeline v1."""

from app.services.expert_pick_eval import pick_hit
from app.services.forum_crawl_service import parse_picks, strip_quote_blocks


def test_stl_dot_separator():
    raw = "04/07/2026 STL : 27.72 ĐB : 02,20,25,52,27,72"
    picks = parse_picks(raw)
    assert picks.get("stl") == ["27", "72"]


def test_de_4so_and_1so():
    raw = (
        "Bệt càng có CT0,5 + kép Cá nhân kết bộ 14,23 To bộ 14 "
        "4 số : 14,41,78,87 1 số : 14 ( 514,3514) Chúc ae mm!"
    )
    picks = parse_picks(raw)
    assert picks.get("de_list") == ["14", "41", "78", "87"]
    assert picks.get("btd_de") == ["14"]


def test_de_list_hits_draw():
    ketqua = {"kq0": "14887", "kqAr": ["87", "27"]}
    assert pick_hit("de_list", ["14", "41", "78", "87"], ketqua) is True
    assert pick_hit("stl", ["27", "72"], ketqua) is True


def test_quote_reply_stripped():
    raw = (
        "Tornado6789 nói: ↑ Lâu lâu vào xin a Đồng ít lộc trang trải c/s "
        "BTL :87 Click to expand..."
    )
    assert parse_picks(raw) == {}
    stripped = strip_quote_blocks(raw)
    assert "BTL" not in stripped or len(stripped) < 15


def test_original_btl_not_stripped():
    raw = "Lâu lâu vào xin a Đồng ít lộc trang trải c/s BTL :87"
    picks = parse_picks(raw)
    assert picks.get("btl") == ["87"]
