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


def _is_login_page_old(html: str) -> bool:
    if re.search(r'class="[^"]*\bLoggedIn\b', html, re.I):
        return False
    if re.search(r'class="[^"]*loginForm', html, re.I):
        return True
    return bool(re.search(r'/login/?"', html, re.I) and re.search(r'name="login"', html, re.I))


def _is_login_page_new(html: str) -> bool:
    if re.search(r'class="[^"]*\bLoggedIn\b', html, re.I):
        return False
    if re.search(r'id="post-\d+"', html, re.I):
        return False
    if THREAD_LINK_RE.search(html):
        return False
    if re.search(r'class="[^"]*loginForm', html, re.I):
        return True
    return bool(
        re.search(r'id="ctrl_pageLogin_login"', html, re.I)
        and re.search(r'id="LoginControl"', html, re.I)
    )


def test_thread_page_not_misclassified_as_login():
    """Public thread HTML has footer login fields — must not block crawl."""
    from app.services.forum_crawl_service import fetch_html

    html = fetch_html(
        "https://forumketqua.net/threads/thao-luan-du-doan-xsmb-thu-3-ngay-07-7-2026.101421/"
    )
    assert 'id="post-' in html
    assert _is_login_page_old(html) is True
    assert _is_login_page_new(html) is False
