from app.services.rbk_crawler import _parse_cau_html, _recommend


SAMPLE_HTML = """
<html><body>
tìm được <span>82</span> cầu
<a class="a_cau">01</a>
<a class="a_cau">10</a>
<a class="a_cau">45</a>
<table>
<tr><td class="col1">01,10</td><td class="col2">6 cầu</td></tr>
<tr><td class="col1">45,54</td><td class="col2">6 cầu</td></tr>
<tr><td class="col1">05,50</td><td class="col2">5 cầu</td></tr>
</table>
Cặp số có nhiều cầu nhất là 01,10: 6 cầu
Trong đó có 27 cầu dài trên 5 ngày
Cầu xuất hiện tại 37 cặp số khác nhau, trong đó có 16 cặp có cầu chạy hơn 5 ngày
</body></html>
"""


def test_parse_cau_html():
    parsed = _parse_cau_html(SAMPLE_HTML)
    assert parsed["total_cau"] == 82
    assert "01" in parsed["unique_numbers"]
    assert parsed["cau_lap"][0] == {"pair": "01,10", "count": 6}
    assert parsed["cau_tren_5ngay"] == 27
    assert parsed["cap_so_khac_nhau"] == 37
    assert parsed["cap_tren_5ngay"] == 16


def test_recommend_dedup_and_sort():
    cau_lap = [
        {"pair": "01,10", "count": 6},
        {"pair": "45,54", "count": 6},
        {"pair": "05,50", "count": 5},
    ]
    recommended, counts = _recommend(cau_lap, min_cau=5)
    assert "01" in recommended
    assert counts["01"] == 6
    assert counts["10"] == 6
    assert recommended[0] in {"01", "10", "45", "54"}
