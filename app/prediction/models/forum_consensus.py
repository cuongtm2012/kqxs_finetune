"""Forum consensus model — scores numbers based on forum dàn 40s/36s/64s picks.

Crawls top users' latest dàn from forumketqua.net and computes:
  - forum_ratio: % of users who include each number
  - top_user_ratio: % of high-win-rate users who include it
  - Combined score: weighted average favoring top users

Only active for DE target (dàn đề). Returns uniform score for LOTO.
"""
from __future__ import annotations

import logging
import re
import urllib.request
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Dict, List, Optional, Set, Tuple

from app.prediction.features import FeatureContext
from app.prediction.constants import ALL_LOTOS

logger = logging.getLogger(__name__)

# ── Forum thread URLs ──────────────────────────────────────────────────────

THREADS = {
    "40s": "https://forumketqua.net/threads/chan-dan-dac-biet-xsmb-40s-khung-4-thang-6-2026.101212/",
    "36s": "https://forumketqua.net/threads/chan-dan-dac-biet-xsmb-36s-khung-5-thang-6-2026.101211/",
    "64s": "https://forumketqua.net/threads/dan-dac-biet-xsmb-64s-thang-6-2026.101209/",
}

# ── Top users (verified win rate >75%) ─────────────────────────────────────
# From scanning June 2026 thread data
TOP_USERS = {
    "danv",          # 12/13 = 92% (40s) + 36s top
    "himle79",       # 15/15 = 100% (40s)
    "Hanhtrinhmoi",  # 9/11 = 82% (40s)
    "Thuoclao6996",  # 10/12 = 83% (40s)
    "emvatoi213",    # top 36s
    "msm43",         # top 40s daily
    "Xuannd",        # consistent performer
    "phipn",         # 40s consistent
    "Binhrau1",      # 40s
    "Rauria",        # 36s top
    "No1.XS",        # 40s
}


def _fetch_page(url: str) -> str:
    """Fetch a single forum page. Returns raw HTML."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        logger.warning("Forum fetch failed for %s: %s", url, e)
        return ""


def _extract_user_dans(html: str) -> Dict[str, Set[str]]:
    """Extract {username: {number_set}} from forum page HTML."""
    user_dans: Dict[str, Set[str]] = {}

    # Find message blocks with data-author
    blocks = re.findall(
        r'<li[^>]*class="message[^"]*"[^>]*data-author="([^"]+)"[^>]*>.*?<div class="messageContent">(.*?)</div>',
        html,
        re.DOTALL,
    )

    for author, content in blocks:
        author = author.strip()
        if author == "quedau1981":
            continue  # admin/stats posts

        # Get text
        text = re.sub(r"<br\s*/?>", "\n", content)
        text = re.sub(r"<[^>]+>", "", text)
        text = text.replace("&nbsp;", " ").replace("&#13;", "")

        # Extract all 2-digit numbers (00-99)
        numbers = set(re.findall(r"\b(\d{2})\b", text))
        # Filter valid game numbers
        numbers = {n for n in numbers if 0 <= int(n) <= 99}

        # Only keep if >= 20 numbers (likely a dàn, not just a STL/BTL post)
        if len(numbers) >= 20:
            user_dans[author] = numbers

    return user_dans


def _crawl_thread(base_url: str, max_pages: int = 3) -> Dict[str, Set[str]]:
    """Crawl multiple pages of a thread, dedup by username (latest post wins)."""
    all_users: Dict[str, Set[str]] = {}
    for page in range(1, max_pages + 1):
        url = f"{base_url}page-{page}" if page > 1 else base_url
        html = _fetch_page(url)
        if not html:
            break
        dans = _extract_user_dans(html)
        # Merge — later pages have newer posts, overwrite older ones
        for author, numbers in dans.items():
            all_users[author] = numbers
        if not dans:
            break  # no more users on this page = no more pages with data
    return all_users


def _extract_all_dans() -> Dict[str, Dict[str, Set[str]]]:
    """Crawl all forum threads and return {thread_key: {user: {numbers}}}."""
    all_dans: Dict[str, Dict[str, Set[str]]] = {}
    for key, url in THREADS.items():
        dans = _crawl_thread(url, max_pages=5)
        if dans:
            all_dans[key] = dans
            logger.info("Forum %s: %d users with dàn (crawled pages)", key, len(dans))
    return all_dans


def _compute_forum_scores() -> Dict[str, float]:
    """Compute forum consensus ratio for each number across all threads.

    Returns {number_string: score} where score = weighted % of users who picked it.
    """
    all_dans = _extract_all_dans()
    if not all_dans:
        return {}

    # Count across all threads
    total_count: Counter = Counter()
    top_count: Counter = Counter()
    total_users = 0
    top_total = 0

    for thread_key, dans in all_dans.items():
        for author, numbers in dans.items():
            total_users += 1
            for n in numbers:
                total_count[n] += 1
            if author in TOP_USERS:
                top_total += 1
                for n in numbers:
                    top_count[n] += 1

    if total_users == 0:
        return {}

    # Score = 0.4 * overall_ratio + 0.6 * top_user_ratio
    # Top user opinion weighted more
    scores: Dict[str, float] = {}
    for num in ALL_LOTOS:
        overall_ratio = total_count.get(num, 0) / total_users
        top_ratio = top_count.get(num, 0) / top_total if top_total > 0 else 0
        scores[num] = 0.4 * overall_ratio + 0.6 * top_ratio

    return scores


# ── Cache ──────────────────────────────────────────────────────────────────

_forum_score_cache: Dict[str, float] = {}
_forum_cache_time: Optional[date] = None


def _get_cached_forum_scores(as_of_date: date) -> Dict[str, float]:
    """Cache forum scores for 1 day to avoid re-crawling."""
    global _forum_score_cache, _forum_cache_time
    if _forum_cache_time != as_of_date or not _forum_score_cache:
        _forum_score_cache = _compute_forum_scores()
        _forum_cache_time = as_of_date
    return _forum_score_cache


# ── Model entry point ──────────────────────────────────────────────────────


def score_forum_consensus(ctx: FeatureContext) -> Dict[str, float]:
    """Score all numbers based on forum dàn 40s/36s/64s consensus.

    For DE: higher score = more forum users include this number.
    For LOTO: returns uniform score (forum dàn is for đề, not lô).

    Returns normalized [0, 1] scores.
    """
    from app.prediction.models.base import normalize_minmax

    raw: Dict[str, float] = {v: 0.0 for v in ctx.universe}

    if ctx.target_type == "de":
        forum_scores = _get_cached_forum_scores(ctx.as_of_date)
        for num in ctx.universe:
            raw[num] = forum_scores.get(num, 0.0)

    # For LOTO/DAU/DIT: no forum signal — return uniform
    # normalize_minmax will handle uniform case

    return normalize_minmax(raw)
