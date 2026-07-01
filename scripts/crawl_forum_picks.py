#!/usr/bin/env python3
"""Crawl forumketqua.net để lấy picks từ các cao thủ XSMB.

Output: JSON stdout với các picks theo ngày + user top.
Chạy trước xsmb_daily_report.py để inject forum data.

Forum DOM researched 27/06/2026:
- Mỗi post trong <li class="message"> chứa:
  - <a class="username">tên_user</a>
  - <blockquote class="messageText">nội_dung_pick</blockquote>
"""

import json
import re
import sys
from datetime import date, timedelta
from urllib.request import Request, urlopen

WEEKDAYS_VI = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]

# Thread IDs (stable for tháng 6/2026)
THREADS = {
    "stl_k2n": "nuoi-song-thu-lo-khung-2-ngay-thang-6-2026.101198",
    "btl_k3n": "topic-chan-nuoi-xsmb-btl-k3n-thang-6-2026.101208",
    "dan_40s": "chan-dan-dac-biet-xsmb-40s-khung-4-thang-6-2026.101212",
    "btl_k5n": "topic-chan-nuoi-xsmb-btl-k5n-thang-6-2026.101183",
    "dan_64s": "dan-dac-biet-xsmb-64s-thang-6-2026.101209",
}

# Top users cần theo dõi
TARGET_USERS = [
    "LangThang1977", "Haiphong27", "T98", "TieuToanPhong",
    "nhcsxh", "gimala", "HoangTin333", "Lookingfor",
    "dogati", "quedau1981", "emvatoi213", "BaMinhBeo",
    "Nhu_Y", "Kubi247", "113",
]

# Known daily thread IDs (mapping: date → thread_id suffix)
KNOWN_DAILY_IDS = {
    date(2026, 6, 22): "thao-luan-du-doan-xsmb-thu-2-ngay-22-6-2026.101326",
    date(2026, 6, 23): "thao-luan-du-doan-xsmb-thu-3-ngay-23-6-2026.101331",
    date(2026, 6, 24): "thao-luan-du-doan-xsmb-thu-4-ngay-24-6-2026.101336",
    date(2026, 6, 25): "thao-luan-du-doan-xsmb-thu-5-ngay-25-6-2026.101341",
    date(2026, 6, 26): "thao-luan-du-doan-xsmb-thu-6-ngay-26-6-2026.101347",
    date(2026, 6, 27): "thao-luan-du-doan-xsmb-thu-7-ngay-27-6-2026.101352",
}

BASE_URL = "https://forumketqua.net"


def fetch_page(url: str) -> str:
    """Fetch HTML from forumketqua."""
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
    })
    try:
        with urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return ""


def extract_posts(html: str) -> list[dict]:
    """Extract {user, content} pairs from forum HTML using regex.
    
    DOM pattern:
    <li class="message" ...>
      <a class="username">USERNAME</a>
      ...
      <blockquote class="messageText">CONTENT</blockquote>
    """
    posts = []
    
    # Find all message blocks
    message_pattern = re.compile(
        r'<a[^>]*class="username"[^>]*>([^<]+)</a>.*?'
        r'<blockquote[^>]*class="messageText[^"]*"[^>]*>(.*?)</blockquote>',
        re.DOTALL
    )
    
    for match in message_pattern.finditer(html):
        user = match.group(1).strip()
        content = match.group(2).strip()
        # Clean HTML tags from content
        content = re.sub(r'<[^>]+>', '', content)
        content = re.sub(r'\s+', ' ', content).strip()
        
        if user and content and len(content) > 15:
            posts.append({"user": user, "content": content})
    
    return posts


def extract_stl(text: str) -> list[str]:
    """Extract STL numbers. Patterns: STL: 68, 86 or STL 68,86 or cặp 68,86."""
    nums = set()
    patterns = [
        r'STL[:\s]+(\d{2})\s*[,/\-]\s*(\d{2})',
        r'stl[:\s]+(\d{2})\s*[,/\-]\s*(\d{2})',
        r'CẶP[:\s]+(\d{2})\s*[,/\-]\s*(\d{2})',
        r'cặp[:\s]+(\d{2})\s*[,/\-]\s*(\d{2})',
    ]
    for pat in patterns:
        for m in re.finditer(pat, text):
            nums.add(m.group(1))
            nums.add(m.group(2))
    return sorted(nums)


def extract_btl(text: str) -> list[str]:
    """Extract BTL number. Pattern: BTL: 31 or btl: 31"""
    nums = set()
    for m in re.finditer(r'BTL[:\s]*(\d{2})', text):
        nums.add(m.group(1))
    return sorted(nums)


def extract_de_info(text: str) -> dict:
    """Extract đề info: chạm, tổng, đầu"""
    result = {"cham": [], "tong": [], "dau": []}
    
    # chạm X, Y, Z
    for m in re.finditer(r'chạm\s+([\d,\s]+?)(?:;|$|\s+tổng|\s+ăn)', text):
        nums = re.findall(r'\d', m.group(1))
        result["cham"].extend(nums)
    
    # tổng X, Y
    for m in re.finditer(r'tổng\s+([\d,\s]+?)(?:;|$|\s+ăn|\s+chạm)', text):
        nums = re.findall(r'\d', m.group(1))
        result["tong"].extend(nums)
    
    # đề đầu X
    for m in re.finditer(r'đề đầu\s+(\d)', text):
        result["dau"].append(m.group(1))
    
    return result


def extract_dan_de(text: str) -> list[str]:
    """Extract dàn đề numbers if there are 30+ two-digit numbers."""
    nums = re.findall(r'\b(\d{2})\b', text)
    valid = [n for n in nums if 0 <= int(n) <= 99]
    if len(valid) >= 30:
        return list(dict.fromkeys(valid))
    return []


def extract_muc_lo(text: str) -> dict:
    """Extract mức lô bảng vàng. Format:
    Mức: 0 (37) số
    9,10,12,...
    """
    result = {}
    current_muc = None
    for line in text.split('\n'):
        line = line.strip()
        m = re.match(r'Mức:\s*(\d+)\s*\(', line)
        if m:
            current_muc = int(m.group(1))
            result[current_muc] = []
            continue
        if current_muc is not None and line:
            nums = re.findall(r'\b(\d{2})\b', line)
            for n in nums:
                if 0 <= int(n) <= 99:
                    result[current_muc].append(n)
    return result


def crawl_thread_page(thread_path: str, page: int = 1) -> list[dict]:
    """Crawl one page of a thread."""
    if page > 1:
        url = f"{BASE_URL}/threads/{thread_path}/page-{page}"
    else:
        url = f"{BASE_URL}/threads/{thread_path}/"
    
    html = fetch_page(url)
    if not html:
        return []
    return extract_posts(html)


def get_daily_thread_id(today: date) -> str:
    """Get daily thread path for today."""
    if today in KNOWN_DAILY_IDS:
        return KNOWN_DAILY_IDS[today]
    
    # For future dates, generate predictably
    weekday = WEEKDAYS_VI[today.weekday()]
    return f"thao-luan-du-doan-xsmb-{weekday.lower().replace(' ', '-')}-ngay-{today.day}-{today.month}-{today.year}.0"


def analyze_stl_k2n(posts: list[dict]) -> dict:
    """Analyze STL K2N thread: find latest picks for each user."""
    users = {}
    
    for post in posts:
        user = post["user"]
        content = post["content"]
        
        picks = extract_stl(content)
        if picks:
            if user not in users:
                users[user] = {"stl": [], "raw": ""}
            users[user]["stl"] = picks
            users[user]["raw"] = content[:200]
    
    return users


def analyze_btl_k3n(posts: list[dict]) -> dict:
    """Analyze BTL K3N thread."""
    users = {}
    
    for post in posts:
        user = post["user"]
        content = post["content"]
        
        picks = extract_btl(content)
        if picks:
            if user not in users:
                users[user] = {"btl": [], "raw": ""}
            users[user]["btl"] = picks
            users[user]["raw"] = content[:200]
    
    return users


def analyze_daily(posts: list[dict]) -> dict:
    """Analyze daily thread: users, mức lô, dàn đề."""
    users = {}
    muc_lo_data = {}
    dan_de_data = []
    
    for post in posts:
        user = post["user"]
        content = post["content"]
        
        # Check for mức lô (mod 113)
        muc = extract_muc_lo(content)
        if muc:
            muc_lo_data = muc
        
        # Check for dàn đề
        dan = extract_dan_de(content)
        if dan:
            dan_de_data = dan
        
        # Check for STL event
        stl = extract_stl(content)
        de_info = extract_de_info(content)
        btl = extract_btl(content)
        
        if stl or btl or any(de_info.values()):
            users[user] = {
                "stl": stl,
                "btl": btl,
                "de": de_info,
            }
    
    return {
        "users": users,
        "muc_lo": muc_lo_data,
        "dan_de": dan_de_data,
    }


def compile_summary(stl_users: dict, btl_users: dict, daily_analysis: dict) -> dict:
    """Compile all picks into summary."""
    summary = {
        "date": date.today().isoformat(),
        "weekday": WEEKDAYS_VI[date.today().weekday()],
        "stl_k2n_users": {},
        "btl_k3n_users": {},
        "daily_users": {},
        "muc_lo": daily_analysis.get("muc_lo", {}),
        "dan_de": daily_analysis.get("dan_de", []),
        "de_cham_leaders": [],
        "picks": {
            "stl_by_user": [],
            "btl_by_user": [],
        }
    }
    
    # Filter target users only
    for user, data in stl_users.items():
        if user in TARGET_USERS:
            summary["stl_k2n_users"][user] = data
    
    for user, data in btl_users.items():
        if user in TARGET_USERS:
            summary["btl_k3n_users"][user] = data
    
    for user, data in daily_analysis.get("users", {}).items():
        if user in TARGET_USERS:
            summary["daily_users"][user] = data
    
    # De cham leaders (gimala, HoangTin333, etc.)
    for user, data in daily_analysis.get("users", {}).items():
        if user in TARGET_USERS and data.get("de", {}).get("cham"):
            summary["de_cham_leaders"].append({
                "user": user,
                "cham": data["de"]["cham"],
            })
    
    # STL frequency
    stl_freq = {}
    for user, data in stl_users.items():
        if user in TARGET_USERS:
            for p in data.get("stl", []):
                if p not in stl_freq:
                    stl_freq[p] = {"count": 0, "users": []}
                stl_freq[p]["count"] += 1
                stl_freq[p]["users"].append(user)
    
    summary["stl_frequency"] = dict(
        sorted(stl_freq.items(), key=lambda x: x[1]["count"], reverse=True)
    )
    
    # BTL frequency
    btl_freq = {}
    for user, data in btl_users.items():
        if user in TARGET_USERS:
            for p in data.get("btl", []):
                if p not in btl_freq:
                    btl_freq[p] = {"count": 0, "users": []}
                btl_freq[p]["count"] += 1
                btl_freq[p]["users"].append(user)
    
    summary["btl_frequency"] = dict(
        sorted(btl_freq.items(), key=lambda x: x[1]["count"], reverse=True)
    )
    
    return summary


def run():
    today = date.today()
    
    # Skip Sunday
    if today.weekday() == 6:
        print(json.dumps({"error": "Chủ nhật không quay XSMB", "date": today.isoformat()}, ensure_ascii=False))
        return
    
    # Crawl STL K2N (page 50 for latest)
    stl_posts = crawl_thread_page(THREADS["stl_k2n"], page=50)
    stl_users = analyze_stl_k2n(stl_posts)
    
    # Crawl BTL K3N (page 20 for latest)
    btl_posts = crawl_thread_page(THREADS["btl_k3n"], page=20)
    btl_users = analyze_btl_k3n(btl_posts)
    
    # Crawl daily thread
    daily_id = get_daily_thread_id(today)
    daily_posts = crawl_thread_page(daily_id)
    daily_analysis = analyze_daily(daily_posts)
    
    summary = compile_summary(stl_users, btl_users, daily_analysis)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
