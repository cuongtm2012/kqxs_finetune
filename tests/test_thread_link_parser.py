"""Forum listing dùng href tương đối threads/slug (không có / đầu)."""
import re

THREAD_LINK_RE = re.compile(
    r'href="(?:(?:https?://[^"]*)?/?)?threads/([^."?#/]+(?:\.[^"?#/]+)?)[^"]*"[^>]*>([^<]+)<',
    re.I | re.S,
)

SAMPLE = """
<a href="threads/thao-luan-du-doan-xsmb-thu-5-ngay-02-7-2026.101394/"
    title=""
    class="PreviewTooltip"
    data-previewUrl="threads/thao-luan-du-doan-xsmb-thu-5-ngay-02-7-2026.101394/preview">THẢO LUẬN, DỰ ĐOÁN XSMB THỨ 5 NGÀY 02/7/2026</a>
"""


def test_relative_thread_href():
    m = THREAD_LINK_RE.search(SAMPLE)
    assert m is not None
    assert m.group(1) == "thao-luan-du-doan-xsmb-thu-5-ngay-02-7-2026.101394"
    assert "02/7/2026" in m.group(2)
