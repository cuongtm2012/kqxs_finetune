"""Forum HTML + pick parsing for backfill (parity with extension parsers)."""

from __future__ import annotations

import html
import logging
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

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache / fallback for monthly thread slugs (channel nuôi khung)
# When infer_monthly_thread_slugs() finds nothing, these provide defaults.
# ---------------------------------------------------------------------------
CACHED_MONTHLY_THREADS: dict[str, dict[str, str]] = {
    "2026-06": {
        "stl_k2n": "nuoi-song-thu-lo-khung-2-ngay-thang-6-2026.101198",
        "btl_k3n": "topic-chan-nuoi-xsmb-btl-k3n-thang-6-2026.101208",
        "btl_k5n": "topic-chan-nuoi-xsmb-btl-k5n-thang-6-2026.101183",
        "dan_40s": "chan-dan-dac-biet-xsmb-40s-khung-4-thang-6-2026.101212",
        "dan_64s": "dan-dac-biet-xsmb-64s-thang-6-2026.101209",
    },
}

# Cache / fallback for daily thao luan slugs
CACHED_DAILY_THAO_LUAN: dict[str, str] = {
    "2026-06-22": "thao-luan-du-doan-xsmb-thu-2-ngay-22-6-2026.101326",
    "2026-06-23": "thao-luan-du-doan-xsmb-thu-3-ngay-23-6-2026.101331",
    "2026-06-24": "thao-luan-du-doan-xsmb-thu-4-ngay-24-6-2026.101336",
    "2026-06-25": "thao-luan-du-doan-xsmb-thu-5-ngay-25-6-2026.101341",
    "2026-06-26": "thao-luan-du-doan-xsmb-thu-6-ngay-26-6-2026.101347",
    "2026-06-27": "thao-luan-du-doan-xsmb-thu-7-ngay-27-6-2026.101352",
}

# Pattern templates for monthly thread titles — used to match on listing pages
_MONTHLY_PATTERNS: dict[str, str] = {
    "stl_k2n": r"nuôi.sống.thủ.lô.khung.2.ngày.tháng.{month}.{year}",
    "btl_k3n": r"chan.nuoi.xsmb.btl.k3n.tháng.{month}.{year}",
    "btl_k5n": r"chan.nuoi.xsmb.btl.k5n.tháng.{month}.{year}",
    "dan_40s": r"chan.dàn.đặc.biệt.xsmb.40s.khung.4.tháng.{month}.{year}",
    "dan_64s": r"dàn.đặc.biệt.xsmb.64s.tháng.{month}.{year}",
}

# Number of listing pages to scan when discovering slugs
_LISTING_PAGES = 3


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
        logger.exception("fetch_page failed for %s", url)
        return ""


def strip_html(text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_forum_text(text: str) -> str:
    """Decode HTML entities from extension stripHtml (e.g. &gt; → >)."""
    return html.unescape(text).replace("\xa0", " ")


def strip_quote_blocks(text: str) -> str:
    """Remove XenForo quote/reply blocks before pick extraction."""
    out = re.sub(
        r"[\w.\-_]+ nói:\s*(?:↑|&uarr;)?[\s\S]*?(?:Click to expand|$)",
        " ",
        text,
        flags=re.I,
    )
    out = re.sub(
        r'<blockquote[^>]*class="[^"]*quote[^"]*"[^>]*>[\s\S]*?</blockquote>',
        " ",
        out,
        flags=re.I,
    )
    return re.sub(r"\s+", " ", out).strip()


def _day_markers(text: str) -> list[tuple[int, int, Optional[int], int]]:
    """Find d/m[/yyyy] day headers — including inline one-line thảo luận posts."""
    out: list[tuple[int, int, Optional[int], int]] = []
    seen: set[int] = set()

    def _add(day: int, month: int, yr: Optional[int], start: int) -> None:
        if not (1 <= day <= 31 and 1 <= month <= 12):
            return
        if start in seen:
            return
        seen.add(start)
        out.append((day, month, yr, start))

    for m in re.finditer(
        r"dự\s*đoán\s+(?:xsmb\s+)?(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{2,4})\b",
        text,
        re.I,
    ):
        yr = int(m.group(3))
        if yr < 100:
            yr += 2000
        _add(int(m.group(1)), int(m.group(2)), yr, m.start(1))

    pat = re.compile(
        r"(?:^|\s)(?:ngày\s+)?(\d{1,2})\s*[./-]\s*(\d{1,2})(?:\s*[./-]\s*(\d{2,4}))?\b",
        re.I,
    )
    for m in pat.finditer(text):
        yr: Optional[int] = None
        if m.group(3):
            yr = int(m.group(3))
            if yr < 100:
                yr += 2000
        _add(int(m.group(1)), int(m.group(2)), yr, m.start(1))

    out.sort(key=lambda x: x[3])
    return out


def day_section_for_target_date(text: str, target_date: str) -> Optional[str]:
    """Slice multi-day thảo luận post to the block for target_date (e.g. 6/7 → 06-07)."""
    y, m, d = map(int, target_date.split("-"))
    markers = _day_markers(text)
    if not markers:
        return None
    for i, (day, month, yr, start) in enumerate(markers):
        if day != d or month != m:
            continue
        if yr is not None and yr != y:
            continue
        end = markers[i + 1][3] if i + 1 < len(markers) else len(text)
        return text[start:end].strip()
    return None


def latest_day_section(text: str) -> str:
    # Support:
    # - "Ngày 02.07.2026" / "Ngày 05/7" / "Ngày 05/7/2026"
    # - "2/7" or "02/07/2026" inline (one-line cumulative thảo luận posts)
    markers = _day_markers(text)
    if not markers:
        return text
    return text[markers[-1][3]:].strip()


def extract_posts_from_html(html: str) -> list[RawPost]:
    posts: list[RawPost] = []
    start_re = re.compile(r'<li[^>]*\bid="post-(\d+)"[^>]*>', re.I)
    starts = list(start_re.finditer(html))
    for i, block in enumerate(starts):
        post_id = block.group(1)
        start = block.start()
        end = starts[i + 1].start() if i + 1 < len(starts) else len(html)
        chunk = html[start:end]
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
    # STL (song thủ lô) should be a single pair. Monthly "nuôi khung" threads
    # contain many historical pairs; we only take the latest pair found.
    last: tuple[str, str] | None = None
    for pat in (
        r"STL[:\s]+(\d{2})\s*[,/.\-]\s*(\d{2})",
        r"CẶP[:\s]+(\d{2})\s*[,/\-]\s*(\d{2})",
        r"cặp[:\s]+(\d{2})\s*[,/\-]\s*(\d{2})",
    ):
        for m in re.finditer(pat, text, re.I):
            last = (m.group(1), m.group(2))
    return [last[0], last[1]] if last else []


def extract_btl(text: str) -> list[str]:
    """Single-line / daily BTL — not multi-Lần chăn nuôi (use extract_btl_for_target_date)."""
    lines = text.split("\n")
    last_btl_line = ""
    for line in lines:
        if re.search(r"BTL", line, re.I):
            last_btl_line = line
    chunk = last_btl_line or text
    nums: set[str] = set()
    for m in re.finditer(r"BTL[:\s]+([\d\s,/.\-]+)", chunk, re.I):
        for n in re.findall(r"\b(\d{2})\b", m.group(1)):
            if int(n) <= 99:
                nums.add(n)
    if not nums:
        nums = {m.group(1) for m in re.finditer(r"BTL[:\s]*(\d{2})", chunk, re.I)}
    return sorted(nums)


def _btl_num_from_lan_section(section: str) -> Optional[str]:
    m = re.search(
        r"(?:CHĂN\s+)?BTL\s*(\d{2})\b|chăn\s*(\d{2})\b",
        section,
        re.I,
    )
    if not m:
        return None
    return m.group(1) or m.group(2)


_LAN_SPLIT_RE = re.compile(
    r"(?=(?:Lần|LẦN)\s*\d+\s*(?::|BTL|CHĂN)|L\d+\s*:)",
    re.I,
)


def split_lan_sections(text: str) -> list[tuple[int, str]]:
    """Split chăn nuôi cumulative post into Lần 1 / L01 blocks."""
    text = normalize_forum_text(text)
    parts = _LAN_SPLIT_RE.split(text)
    out: list[tuple[int, str]] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        m = re.match(r"(?:Lần|LẦN)\s*(\d+)\s*:\s*(.*)", part, re.I | re.S)
        if m:
            out.append((int(m.group(1)), m.group(2).strip()))
            continue
        m = re.match(r"(?:Lần|LẦN)\s*(\d+)\s+(.*)", part, re.I | re.S)
        if m:
            out.append((int(m.group(1)), m.group(2).strip()))
            continue
        m = re.match(r"L(\d+)\s*:\s*(.*)", part, re.I | re.S)
        if m:
            out.append((int(m.group(1)), m.group(2).strip()))
    return out


def parse_lan_day_range(
    fragment: str,
    default_year: int,
    default_month: int,
) -> Optional[tuple[int, int, int, int]]:
    """Parse khung ngày in a Lần block → (year, month, day_start, day_end)."""
    fragment = normalize_forum_text(fragment)

    def _valid(yr: int, mo: int, d0: int, d1: int) -> Optional[tuple[int, int, int, int]]:
        try:
            date(yr, mo, d0)
            date(yr, mo, d1)
            return yr, mo, d0, d1
        except ValueError:
            return None

    # 01/07 -> 03/07 or 01/07-05/07 (full dd/mm both sides)
    m = re.search(
        r"(?:từ|tu)\s*(\d{1,2})\s*/\s*(\d{1,2})\s*(?:->|[-→>]+)\s*(\d{1,2})\s*/\s*(\d{1,2})\b",
        fragment,
        re.I,
    )
    if m:
        d0, mo, d1, mo2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        if mo == mo2:
            got = _valid(default_year, mo, d0, d1)
            if got:
                return got

    # từ 01-> 03 / từ 04-> 06 (day only, no month suffix)
    m = re.search(r"(?:từ|tu)\s*(\d{1,2})\s*[>→\-]+\s*(\d{1,2})\b", fragment, re.I)
    if m:
        got = _valid(default_year, default_month, int(m.group(1)), int(m.group(2)))
        if got:
            return got

    # (TỪ 01-05) K5N style — day range without month
    m = re.search(r"(?:từ|tu)\s*(\d{1,2})\s*-\s*(\d{1,2})\b", fragment, re.I)
    if m:
        got = _valid(default_year, default_month, int(m.group(1)), int(m.group(2)))
        if got:
            return got

    patterns = [
        r"(?:từ|tu)\s*(\d{1,2})\s*[>→\-]\s*(\d{1,2})\s*/\s*(\d{1,2})",
        r"\(\s*(?:từ|tu)?\s*(\d{1,2})\s*[>→\-]\s*(\d{1,2})\s*/\s*(\d{1,2})\s*\)",
        r"(?:từ|tu)\s*(\d{1,2})\s*-\s*(\d{1,2})\s*/\s*(\d{1,2})",
        r"\(\s*(\d{1,2})\s*-\s*(\d{1,2})\s*/\s*(\d{1,2})\s*\)",
        r"(\d{1,2})\s*-\s*(\d{1,2})\s*/\s*(\d{1,2})",
        r"\(\s*(\d{1,2})\s*-\s*(\d{1,2})\s*\)",
    ]
    for i, pat in enumerate(patterns):
        m = re.search(pat, fragment, re.I)
        if not m:
            continue
        d0, d1 = int(m.group(1)), int(m.group(2))
        if i == len(patterns) - 1:
            mo, yr = default_month, default_year
        else:
            mo = int(m.group(3))
            yr = default_year
        got = _valid(yr, mo, d0, d1)
        if got:
            return got
    return None


def extract_btl_for_target_date(text: str, target_date: str) -> Optional[list[str]]:
    """
    Chăn nuôi BTL K3N: mỗi Lần = 1 số + khung ngày.
    Returns None if not a Lần-style post (caller uses extract_btl).
  """
    sections = split_lan_sections(text)
    if not sections:
        return None
    if not any(_btl_num_from_lan_section(s) for _, s in sections):
        return None

    y, m, d = map(int, target_date.split("-"))
    cur = date(y, m, d)
    best: Optional[tuple[int, str]] = None

    for lan_no, section in sections:
        num = _btl_num_from_lan_section(section)
        if not num:
            continue
        dr = parse_lan_day_range(section, y, m)
        if not dr:
            continue
        yr, mo, d0, d1 = dr
        if mo != m or yr != y:
            continue
        try:
            if date(yr, mo, d0) <= cur <= date(yr, mo, d1):
                if best is None or lan_no >= best[0]:
                    best = (lan_no, num)
        except ValueError:
            continue

    return [best[1]] if best else []


def extract_std_de(text: str) -> list[str]:
    # Preserve pair semantics: return tokens like "59-89" (not flattened numbers).
    # A user can "nuôi" multiple pairs in one post; keep all unique pairs in appearance order.
    out: list[str] = []
    for m in re.finditer(r"(?:STĐ|STD)\s*[:\s]+(\d{2})\s*[,/\-]\s*(\d{2})", text, re.I):
        token = f"{m.group(1)}-{m.group(2)}"
        if token not in out:
            out.append(token)
    return out


def extract_btd_de(text: str) -> list[str]:
    nums: set[str] = set()
    for m in re.finditer(r"(?:BTĐ|BTD)\s*[:\s]+(\d{2})\b", text, re.I):
        nums.add(m.group(1))
    return sorted(nums)


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
    # Lookingfor-style shorthand: "ĐB: CT1,6 (CT2,7; CT3,8) hạ C13458"
    for m in re.finditer(r"đb\s*:\s*([\s\S]*?)(?=bộ\s*:|20\s*em|1s:|3,4d:|$)", text, re.I):
        chunk = m.group(1)
        for ct in re.finditer(r"CT\s*([\d,\s]+)", chunk, re.I):
            result["cham"].extend(re.findall(r"\d", ct.group(1)))
        for h in re.finditer(r"(?:hạ\s*)?C\s*([0-9,\s]+)", chunk, re.I):
            result["cham"].extend(re.findall(r"\d", h.group(1)))
    for key in result:
        result[key] = list(dict.fromkeys(result[key]))
    return result


def extract_de_list(text: str) -> list[str]:
    """Casual đề: 'Đề 11,66' or '4 số : 14,41,78,87'."""
    nums: set[str] = set()
    for m in re.finditer(r"4\s*số\s*:\s*([0-9,\s]+)", text, re.I):
        for n in re.findall(r"\b(\d{2})\b", m.group(1)):
            if 0 <= int(n) <= 99:
                nums.add(n)
    for m in re.finditer(r"(?:^|\n)\s*Đề\s+([0-9,\s]+?)(?:\n|$|&nbsp|\s{2,})", text, re.I):
        for n in re.findall(r"\b(\d{2})\b", m.group(1)):
            if 0 <= int(n) <= 99:
                nums.add(n)
    for m in re.finditer(r"Đề\s*[:：]\s*([0-9,\s]+?)(?:\n|$|&nbsp|\s{2,})", text, re.I):
        for n in re.findall(r"\b(\d{2})\b", m.group(1)):
            if 0 <= int(n) <= 99:
                nums.add(n)
    return sorted(nums) if len(nums) >= 2 else sorted(nums)


def extract_de_1so(text: str) -> list[str]:
    nums: set[str] = set()
    for m in re.finditer(r"1\s*số\s*:\s*(\d{2})\b", text, re.I):
        nums.add(m.group(1))
    return sorted(nums)


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


def _dan_extract_chunk(text: str) -> str:
    """Prefer numbers listed after a Dàn đề header — avoids BTL/STL/date pollution."""
    m = re.search(r"(?:dàn|dan)\s*(?:đề|de)(?:\s+\d+\s*s(?:ố)?)?\s*:\s*", text, re.I)
    if m:
        return text[m.end():]
    m = re.search(r"(?:dàn|dan)\s*(?:đề|de)(?:\s+\d+\s*s(?:ố)?)\s+", text, re.I)
    if m:
        return text[m.end():]
    m = re.search(r"(?:dàn|dan)\s*(?:đề|de)[^\n]*", text, re.I)
    if m:
        return text[m.end():]
    lines = []
    for line in text.split("\n"):
        s = line.strip()
        if re.match(r"\d{1,2}\s*[./-]\s*\d", s):
            continue
        if re.search(r"\b(?:BTL|STL)\b", s, re.I):
            continue
        lines.append(line)
    return "\n".join(lines)


def extract_dan_de(text: str) -> list[str]:
    chunk = _dan_extract_chunk(text)
    nums = re.findall(r"\b(\d{2})\b", chunk)
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


def parse_picks(raw: str, thread_title: str = "", target_date: str = "") -> dict:
    stripped = strip_quote_blocks(normalize_forum_text(raw))
    if len(stripped) < 8 and not re.search(r"\b(?:BTL|STL|Btl|Stl)\b", stripped, re.I):
        return {}
    if target_date:
        scoped = day_section_for_target_date(stripped, target_date) or latest_day_section(stripped)
    else:
        scoped = latest_day_section(stripped)
    picks: dict = {}
    stl = extract_stl(scoped)
    if stl:
        picks["stl"] = stl
    btl: Optional[list[str]] = None
    if target_date:
        btl = extract_btl_for_target_date(stripped, target_date)
    if not btl:
        btl = extract_btl(scoped)
    if btl:
        picks["btl"] = btl
    std_de = extract_std_de(scoped)
    if std_de:
        picks["std_de"] = std_de
    btd_de = extract_btd_de(scoped)
    btd_de = sorted(set(btd_de) | set(extract_de_1so(scoped)))
    if btd_de:
        picks["btd_de"] = btd_de
    de = extract_de_info(scoped)
    if any(de.values()):
        picks["de"] = de
    btd = extract_btd(scoped)
    if btd:
        picks["btd"] = btd
    btd_dau = extract_btd_dau(scoped)
    if btd_dau:
        picks["btd_dau"] = btd_dau
    dan = extract_dan_de(scoped)
    if dan:
        picks["dan_de"] = dan
        picks["dan_pick_type"] = infer_dan_pick_type(len(dan), thread_title, scoped)
    de_list = extract_de_list(scoped)
    if de_list:
        picks["de_list"] = de_list
    muc = extract_muc_lo(scoped)
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


def synthetic_posted_at_ms(target_date: str) -> int:
    start_ms, end_ms = window_bounds_ms(target_date)
    return start_ms + max(1, (end_ms - start_ms) // 2)


def parse_lan_range_end_date(fragment: str, year: int, month: int) -> Optional[str]:
    """Parse 'Từ 1-4/6' or 'Từ 30/6' → target_date (last day of khung)."""
    m = re.search(
        r"từ\s+(\d{1,2})(?:\s*-\s*(\d{1,2}))?\s*/\s*(\d{1,2})\b",
        fragment,
        re.I,
    )
    if not m:
        return None
    d_end = int(m.group(2) or m.group(1))
    m_in = int(m.group(3))
    if m_in != month:
        return None
    try:
        d = date(year, month, d_end)
        if d.weekday() == 6:
            d -= timedelta(days=1)
        return d.isoformat()
    except ValueError:
        return None


def split_chan_nuoi_lan_sections(text: str) -> list[tuple[int, str]]:
    return split_lan_sections(text)


def expand_chan_nuoi_posts_by_lan(
    raw_posts: list[tuple[str, str, RawPost]],
    year: int,
    month: int,
) -> dict[str, list[tuple[str, str, RawPost]]]:
    """Parse cumulative Lần N blocks in monthly chan nuoi → picks per draw day."""
    posts_by_user_thread: dict[tuple[str, str], list[RawPost]] = {}
    for forum, slug, raw in raw_posts:
        if forum != "chan_nuoi":
            continue
        posts_by_user_thread.setdefault((raw.user.lower(), slug), []).append(raw)

    by_date: dict[str, dict[tuple[str, str], tuple[int, tuple[str, str, RawPost]]]] = {}

    for (_user_lower, slug), posts in posts_by_user_thread.items():
        posts.sort(key=lambda p: int(p.post_id))
        user = posts[-1].user
        lan_best: dict[int, tuple[str, list[str]]] = {}
        for post in posts:
            for lan_no, section in split_chan_nuoi_lan_sections(post.raw_content):
                btl_num = _btl_num_from_lan_section(section)
                dr = parse_lan_day_range(section, year, month)

                if btl_num and dr:
                    dr_y, dr_m, d0, d1 = dr
                    for day in range(d0, d1 + 1):
                        try:
                            td = date(dr_y, dr_m, day)
                            if td.weekday() == 6:
                                continue
                            tkey = td.isoformat()
                            bucket = by_date.setdefault(tkey, {})
                            pick_key = (user, slug)
                            synth = RawPost(
                                post_id=f"{posts[-1].post_id}-lan{lan_no}-btl-{tkey}",
                                user=user,
                                posted_at_ms=synthetic_posted_at_ms(tkey),
                                raw_content=f"BTL {btl_num}",
                            )
                            prev = bucket.get(pick_key)
                            if prev and prev[0] >= lan_no:
                                continue
                            bucket[pick_key] = (lan_no, ("chan_nuoi", slug, synth))
                        except ValueError:
                            continue
                    continue

                target = parse_lan_range_end_date(section, year, month)
                if not target:
                    continue
                dan = extract_dan_de(section)
                if len(dan) < 30:
                    continue
                lan_best[lan_no] = (target, dan)

        for lan_no, (target, dan) in lan_best.items():
            scoped = f"Ngày {target}: " + ", ".join(dan)
            synth = RawPost(
                post_id=f"{posts[-1].post_id}-lan{lan_no}",
                user=user,
                posted_at_ms=synthetic_posted_at_ms(target),
                raw_content=scoped,
            )
            bucket = by_date.setdefault(target, {})
            pick_key = (user, slug)
            prev = bucket.get(pick_key)
            if prev and prev[0] >= lan_no:
                continue
            bucket[pick_key] = (lan_no, ("chan_nuoi", slug, synth))

    return {
        day: [entry[1] for entry in sorted(bucket.values(), key=lambda x: x[0])]
        for day, bucket in by_date.items()
    }


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


def infer_monthly_thread_slugs(year: int, month: int) -> dict[str, str]:
    """Discover monthly channel nuôi thread slugs by crawling listing pages.

    Crawls the du-doan-xsmb forum listing (page-1 through page-{_LISTING_PAGES})
    looking for thread titles that match known monthly patterns for this year/month.
    Falls back to CACHED_MONTHLY_THREADS if no matches found in the listing.

    Returns dict mapping keys like 'stl_k2n', 'btl_k3n', etc. to their slug strings.
    """
    cache_key = f"{year}-{month:02d}"
    if cache_key in CACHED_MONTHLY_THREADS:
        logger.info("Using cached monthly threads for %s", cache_key)
        return dict(CACHED_MONTHLY_THREADS[cache_key])

    listing = f"{BASE_URL}/forums/du-doan-xsmb/"
    results: dict[str, str] = {}

    for page in range(1, _LISTING_PAGES + 1):
        url = listing if page == 1 else f"{listing}page-{page}"
        html = fetch_html(url)
        if not html:
            continue

        # Build compiled patterns for each key
        for key, template in _MONTHLY_PATTERNS.items():
            if key in results:
                continue  # already found
            pattern_str = template.format(year=year, month=month)
            # pattern_str uses '.' as word separators — convert to \\s* for flexible matching
            pattern_re = re.compile(
                pattern_str.replace(".", r"\s*"),
                re.I,
            )
            for m_link in re.finditer(
                r'href="(?:(?:https?://[^"]*)?/?)?threads/([^."?#/]+(?:\.[^"?#/]+)?)[^"]*"[^>]*>([^<]+)<',
                html,
                re.I | re.S,
            ):
                slug = m_link.group(1)
                title = re.sub(r"\s+", " ", m_link.group(2)).strip()
                if pattern_re.search(title):
                    results[key] = slug
                    break

        if len(results) == len(_MONTHLY_PATTERNS):
            break  # all found

    if results:
        logger.info("Discovered %d monthly thread slugs for %s", len(results), cache_key)
        return results

    logger.warning(
        "No monthly thread slugs found for %s on listing pages, "
        "extend CACHED_MONTHLY_THREADS if this month is expected",
        cache_key,
    )
    return {}


def discover_daily_thread_slug(target_date: str, forum: str = "thao_luan") -> Optional[str]:
    if target_date in CACHED_DAILY_THAO_LUAN:
        return CACHED_DAILY_THAO_LUAN[target_date]

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
    for page in range(1, _LISTING_PAGES + 1):
        url = listing if page == 1 else f"{listing}page-{page}"
        html = fetch_html(url)
        for m_link in re.finditer(
            r'href="(?:(?:https?://[^"]*)?/?)?threads/([^."?#/]+(?:\.[^"?#/]+)?)[^"]*"[^>]*>([^<]+)<',
            html,
            re.I | re.S,
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
        picks = parse_picks(raw.raw_content, slug, target_date)
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
