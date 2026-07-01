"""Forum HTML + pick parsing for backfill (parity with extension parsers)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

BASE_URL = "https://forumketqua.net"
TZ = ZoneInfo("Asia/Ho_Chi_Minh")
COLLECT_START = (18, 30)
COLLECT_END = (18, 0)

JUNE_2026_THREADS = {
    "stl_k2n": "nuoi-song-thu-lo-khung-2-ngay-thang-6-2026.101198",
    "btl_k3n": "topic-chan-nuoi-xsmb-btl-k3n-thang-6-2026.101208",
    "btl_k5n": "topic-chan-nuoi-xsmb-btl-k5n-thang-6-2026.101183",
    "dan_40s": "chan-dan-dac-biet-xsmb-40s-khung-4-thang-6-2026.101212",
    "dan_64s": "dan-dac-biet-xsmb-64s-thang-6-2026.101209",
}

KNOWN_DAILY_THAO_LUAN = {
    "2026-06-22": "thao-luan-du-doan-xsmb-thu-2-ngay-22-6-2026.101326",
    "2026-06-23": "thao-luan-du-doan-xsmb-thu-3-ngay-23-6-2026.101331",
    "2026-06-24": "thao-luan-du-doan-xsmb-thu-4-ngay-24-6-2026.101336",
    "2026-06-25": "thao-luan-du-doan-xsmb-thu-5-ngay-25-6-2026.101341",
    "2026-06-26": "thao-luan-du-doan-xsmb-thu-6-ngay-26-6-2026.101347",
    "2026-06-27": "thao-luan-du-doan-xsmb-thu-7-ngay-27-6-2026.101352",
}


@dataclass
class RawPost:
    post_id: str
    user: str
    posted_at_ms: int
    raw_content: str


def fetch_html(url: str) -> str:
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "vi-VN,vi;q=0.9",
        },
    )
    try:
        with urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def strip_html(text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_posts_from_html(html: str) -> list[RawPost]:
    posts: list[RawPost] = []
    block_re = re.compile(r'<li[^>]*\bid="post-(\d+)"[^>]*>([\s\S]*?)</li>', re.I)
    for block in block_re.finditer(html):
        post_id = block.group(1)
        chunk = block.group(2)
        user = (
            re.search(r'data-author="([^"]+)"', chunk, re.I)
            or re.search(r'class="username"[^>]*>([^<]+)<', chunk, re.I)
        )
        if not user:
            continue
        user = user.group(1).strip()
        raw_time = int(re.search(r'data-time="(\d+)"', chunk, re.I).group(1) if re.search(r'data-time="(\d+)"', chunk, re.I) else 0)
        time_ms = raw_time * 1000 if 0 < raw_time < 100_000_000_000 else raw_time
        content_m = re.search(
            r'<blockquote[^>]*class="messageText[^"]*"[^>]*>([\s\S]*?)</blockquote>',
            chunk,
            re.I,
        )
        if not content_m:
            continue
        raw = strip_html(content_m.group(1))
        if not user or len(raw) < 15:
            continue
        posts.append(RawPost(post_id, user, time_ms or 0, raw))
    return posts


def get_last_page(html: str) -> int:
    pages = [int(m.group(1)) for m in re.finditer(r"page-(\d+)", html, re.I)]
    return max(pages) if pages else 1


def extract_stl(text: str) -> list[str]:
    nums: set[str] = set()
    for pat in (
        r"STL[:\s]+(\d{2})\s*[,/\-]\s*(\d{2})",
        r"CẶP[:\s]+(\d{2})\s*[,/\-]\s*(\d{2})",
        r"cặp[:\s]+(\d{2})\s*[,/\-]\s*(\d{2})",
    ):
        for m in re.finditer(pat, text, re.I):
            nums.add(m.group(1))
            nums.add(m.group(2))
    return sorted(nums)


def extract_btl(text: str) -> list[str]:
    return sorted({m.group(1) for m in re.finditer(r"BTL[:\s]*(\d{2})", text, re.I)})


def extract_de_info(text: str) -> dict:
    result: dict[str, list[str]] = {"cham": [], "tong": [], "dau": []}
    for m in re.finditer(r"chạm\s+([\d,\s]+?)(?:;|$|\s+tổng|\s+ăn)", text, re.I):
        result["cham"].extend(re.findall(r"\d", m.group(1)))
    for m in re.finditer(r"tổng\s+([\d,\s]+?)(?:;|$|\s+ăn|\s+chạm)", text, re.I):
        result["tong"].extend(re.findall(r"\d", m.group(1)))
    for m in re.finditer(
        r"đề\s*đầu\s+([\d,\s]+?)(?:\s+gút|;|$|\s+tổng|\s+chạm)", text, re.I
    ):
        if re.search(r"đặc\s*biệt", m.group(0), re.I):
            continue
        result["dau"].extend(re.findall(r"\d", m.group(1)))
    if not result["dau"]:
        for m in re.finditer(r"đề\s*đầu\s+(\d)", text, re.I):
            if re.search(r"đặc\s*biệt", m.group(0), re.I):
                continue
            result["dau"].append(m.group(1))
    for key in result:
        result[key] = list(dict.fromkeys(result[key]))
    return result


def _parse_btd_numbers(chunk: str) -> list[str]:
    nums: set[str] = set()
    nums.update(m.group(1) for m in re.finditer(r"[bB](\d{2})\b", chunk))
    for m in re.finditer(r"(?:^|[\s,])(\d{2})\b", chunk):
        if int(m.group(1)) <= 99:
            nums.add(m.group(1))
    return sorted(nums)


def _parse_btd_dau_digits(chunk: str) -> list[str]:
    digits: list[str] = []
    for m in re.finditer(r"[bB](\d+)", chunk):
        digits.extend(list(m.group(1)))
    return sorted(set(digits))


def extract_btd(text: str) -> list[str]:
    nums: set[str] = set()
    for m in re.finditer(
        r"đề\s*đặc\s*biệt\s*[:\s]+([\s\S]*?)(?=đề\s*đầu\s*đặc\s*biệt|;|$)",
        text,
        re.I,
    ):
        nums.update(_parse_btd_numbers(m.group(1)))
    for m in re.finditer(r"\bBTD\s*[:\s]+([\s\S]*?)(?=;|$|\n)", text, re.I):
        nums.update(_parse_btd_numbers(m.group(1)))
        for n in re.findall(r"\b(\d{2})\b", m.group(1)):
            if int(n) <= 99:
                nums.add(n)
    return sorted(nums)


def extract_btd_dau(text: str) -> list[str]:
    digits: set[str] = set()
    for m in re.finditer(
        r"đề\s*đầu\s*đặc\s*biệt\s*[:\s]+([\s\S]*?)(?=;|$)", text, re.I
    ):
        digits.update(_parse_btd_dau_digits(m.group(1)))
    return sorted(digits)


def infer_dan_pick_type(count: int, thread_title: str = "", text: str = "") -> str:
    blob = f"{thread_title} {text}".lower()
    if "64s" in blob or "64 s" in blob or count >= 58:
        return "dan_64s"
    if "36s" in blob or "36 s" in blob:
        return "dan_36s"
    if "40s" in blob or "40 s" in blob or count >= 38:
        return "dan_40s"
    if count >= 30:
        return "dan_36s"
    return "dan_de"


def extract_dan_de(text: str) -> list[str]:
    nums = re.findall(r"\b(\d{2})\b", text)
    valid = [n for n in nums if 0 <= int(n) <= 99]
    if len(valid) < 30:
        return []
    return list(dict.fromkeys(valid))


def extract_muc_lo(text: str) -> dict[int, list[str]]:
    result: dict[int, list[str]] = {}
    current: Optional[int] = None
    for line in text.split("\n"):
        line = line.strip()
        m = re.match(r"Mức:\s*(\d+)\s*\(", line, re.I)
        if m:
            current = int(m.group(1))
            result[current] = []
            continue
        if current is not None and line:
            for n in re.findall(r"\b(\d{2})\b", line):
                if 0 <= int(n) <= 99:
                    result[current].append(n)
    return result


def parse_picks(raw: str, thread_title: str = "") -> dict:
    picks: dict = {}
    stl = extract_stl(raw)
    if stl:
        picks["stl"] = stl
    btl = extract_btl(raw)
    if btl:
        picks["btl"] = btl
    de = extract_de_info(raw)
    if any(de.values()):
        picks["de"] = de
    btd = extract_btd(raw)
    if btd:
        picks["btd"] = btd
    btd_dau = extract_btd_dau(raw)
    if btd_dau:
        picks["btd_dau"] = btd_dau
    dan = extract_dan_de(raw)
    if dan:
        picks["dan_de"] = dan
        picks["dan_pick_type"] = infer_dan_pick_type(len(dan), thread_title, raw)
    muc = extract_muc_lo(raw)
    if muc:
        picks["muc_lo"] = muc
    return picks


def window_bounds_ms(target_date: str) -> tuple[int, int]:
    y, m, d = map(int, target_date.split("-"))
    target = date(y, m, d)
    prev = target - timedelta(days=1)
    start_dt = datetime(
        prev.year, prev.month, prev.day,
        COLLECT_START[0], COLLECT_START[1], tzinfo=TZ,
    )
    end_dt = datetime(
        y, m, d, COLLECT_END[0], COLLECT_END[1], tzinfo=TZ,
    )
    return int(start_dt.timestamp() * 1000), int(end_dt.timestamp() * 1000)


def collect_window_labels(target_date: str) -> tuple[str, str]:
    y, m, d = map(int, target_date.split("-"))
    target = date(y, m, d)
    prev = target - timedelta(days=1)
    start = f"{prev.isoformat()}T18:30:00+07:00"
    end = f"{target_date}T18:00:00+07:00"
    return start, end


def crawl_thread_all_pages(slug: str) -> list[RawPost]:
    first_url = f"{BASE_URL}/threads/{slug}/"
    html = fetch_html(first_url)
    if not html:
        return []
    last_page = get_last_page(html)
    all_posts: list[RawPost] = []
    seen: set[str] = set()
    for page in range(1, last_page + 1):
        url = first_url if page == 1 else f"{BASE_URL}/threads/{slug}/page-{page}"
        page_html = html if page == 1 else fetch_html(url)
        for p in extract_posts_from_html(page_html):
            if p.post_id in seen:
                continue
            seen.add(p.post_id)
            all_posts.append(p)
    return all_posts


def discover_daily_thread_slug(target_date: str, forum: str = "thao_luan") -> Optional[str]:
    if target_date in KNOWN_DAILY_THAO_LUAN:
        return KNOWN_DAILY_THAO_LUAN[target_date]

    y, m, d = map(int, target_date.split("-"))
    pattern = r"MỞ BÁT" if forum == "mo_bat" else r"THẢO LUẬN.*NGÀY"
    listing = (
        f"{BASE_URL}/forums/khu-mo-bat.13/"
        if forum == "mo_bat"
        else f"{BASE_URL}/forums/du-doan-xsmb/"
    )
    date_tokens = [
        f"{d}/{m}/{y}",
        f"{d}.{m}.{y}",
        f"{d}-{m}-{y}",
        f"{d}/{m}",
    ]
    for page in (1, 2):
        url = listing if page == 1 else f"{listing}page-{page}"
        html = fetch_html(url)
        for m_link in re.finditer(
            r'href="(?:https?://[^"]*)?/threads/([^."?#/]+(?:\.[^"?#/]+)?)[^"]*"[^>]*>([^<]+)<',
            html,
            re.I,
        ):
            slug = m_link.group(1)
            title = re.sub(r"\s+", " ", m_link.group(2)).strip().upper()
            if not re.search(pattern, title, re.I):
                continue
            if any(tok in title for tok in (t.upper() for t in date_tokens)):
                return slug
    return None


def posts_to_session_dict(
    target_date: str,
    raw_posts: list[tuple[str, str, RawPost]],
) -> dict:
    start_ms, end_ms = window_bounds_ms(target_date)
    window_start, window_end = collect_window_labels(target_date)
    posts: dict[str, dict] = {}

    for forum, slug, raw in raw_posts:
        if raw.posted_at_ms < start_ms or raw.posted_at_ms >= end_ms:
            continue
        picks = parse_picks(raw.raw_content, slug)
        if not picks:
            continue
        posts[raw.post_id] = {
            "post_id": raw.post_id,
            "thread_id": slug,
            "forum": forum,
            "user": raw.user,
            "posted_at": datetime.fromtimestamp(raw.posted_at_ms / 1000, tz=timezone.utc).isoformat(),
            "posted_at_ms": raw.posted_at_ms,
            "raw_content": raw.raw_content,
            "picks": picks,
        }

    return {
        "target_date": target_date,
        "window_start": window_start,
        "window_end": window_end,
        "finalized_at": datetime.now(timezone.utc).isoformat(),
        "posts": posts,
        "summary": {"target_date": target_date, "date": target_date},
    }
