import json
import logging
import re
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

from app.config import settings
from app.utils.http_util import obtain_content

logger = logging.getLogger(__name__)

CACHE_DIR = Path("/tmp/rbk_cache")
CACHE_TTL = timedelta(days=1)

RBK_NET_CAU_URL = (
    "https://rongbachkim.net/soicau.html?submit=1&setmode=full&exactlimit=0"
    "&limit={limit}&ngay={ngay}&nhay=1&lon=1"
)


def _format_ngay(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _cache_path(d: date, limit: int) -> Path:
    return CACHE_DIR / f"{d.isoformat()}_{limit}.json"


def _read_cache(d: date, limit: int) -> Optional[dict]:
    path = _cache_path(d, limit)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        cached_at = datetime.fromisoformat(payload["cached_at"])
        if datetime.now() - cached_at > CACHE_TTL:
            return None
        return payload["data"]
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def _write_cache(d: date, limit: int, data: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(d, limit)
    path.write_text(
        json.dumps({"cached_at": datetime.now().isoformat(), "data": data}, ensure_ascii=False),
        encoding="utf-8",
    )


def _build_url(limit: int, ngay: str) -> str:
    return RBK_NET_CAU_URL.format(limit=limit, ngay=ngay)


def _parse_cau_html(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    total_cau = 0
    for pattern in (
        r"tìm được\s*(\d+)\s*cầu",
        r"<span>\s*(\d+)\s*</span>\s*cầu",
    ):
        match = re.search(pattern, html if "<span>" in pattern else text, re.I)
        if match:
            total_cau = int(match.group(1))
            break

    unique_numbers: list[str] = []
    for element in soup.select("a.a_cau"):
        val = re.sub(r"\D", "", element.get_text(strip=True))[-2:].zfill(2)
        if len(val) == 2 and val not in unique_numbers:
            unique_numbers.append(val)

    cau_lap: list[dict] = []
    for row in soup.select("tr"):
        col1 = row.select_one("td.col1")
        col2 = row.select_one("td.col2")
        if not col1 or not col2:
            continue
        pair = col1.get_text(strip=True)
        count_match = re.search(r"(\d+)", col2.get_text())
        if pair and count_match:
            cau_lap.append({"pair": pair, "count": int(count_match.group(1))})

    cap_nhieu_cau_nhat = ""
    cap_match = re.search(
        r"Cặp số có nhiều cầu nhất là\s*([^<]+)",
        html,
        re.I,
    )
    if cap_match:
        cap_nhieu_cau_nhat = BeautifulSoup(cap_match.group(1), "html.parser").get_text(strip=True)

    cau_tren_5ngay = 0
    m = re.search(r"có\s*(\d+)\s*cầu dài trên 5 ngày", text, re.I)
    if m:
        cau_tren_5ngay = int(m.group(1))

    cap_so_khac_nhau = 0
    m = re.search(r"(\d+)\s*cặp số khác nhau", text, re.I)
    if m:
        cap_so_khac_nhau = int(m.group(1))

    cap_tren_5ngay = 0
    m = re.search(r"có\s*(\d+)\s*cặp có cầu chạy hơn 5 ngày", text, re.I)
    if m:
        cap_tren_5ngay = int(m.group(1))

    return {
        "total_cau": total_cau,
        "cau_lap": cau_lap,
        "unique_numbers": unique_numbers,
        "cap_nhieu_cau_nhat": cap_nhieu_cau_nhat,
        "cau_tren_5ngay": cau_tren_5ngay,
        "cap_so_khac_nhau": cap_so_khac_nhau,
        "cap_tren_5ngay": cap_tren_5ngay,
    }


def _recommend(cau_lap: list[dict], min_cau: int) -> tuple[list[str], dict[str, int]]:
    number_counts: dict[str, int] = defaultdict(int)
    for item in cau_lap:
        if item["count"] < min_cau:
            continue
        for part in item["pair"].split(","):
            lot = part.strip().zfill(2)[-2:]
            if len(lot) == 2:
                number_counts[lot] += item["count"]
    recommended = sorted(number_counts.keys(), key=lambda x: (-number_counts[x], x))
    return recommended, dict(number_counts)


def crawl_rbk_cau(limit: int, ngay: str) -> dict:
    url = _build_url(limit, ngay)
    html = obtain_content(url)
    if not html:
        url = settings.caudep_url % (limit, ngay, 1, 1)
        html = obtain_content(url)
    if not html:
        return {
            "error": "crawl_failed",
            "total_cau": 0,
            "cau_lap": [],
            "unique_numbers": [],
            "cap_nhieu_cau_nhat": "",
            "cau_tren_5ngay": 0,
            "cap_so_khac_nhau": 0,
            "cap_tren_5ngay": 0,
            "recommended": [],
            "number_counts": {},
        }
    parsed = _parse_cau_html(html)
    recommended, number_counts = _recommend(parsed["cau_lap"], min_cau=1)
    if not recommended and parsed["unique_numbers"]:
        recommended = parsed["unique_numbers"]
    parsed["recommended"] = recommended
    parsed["number_counts"] = number_counts
    parsed["source_url"] = url
    return parsed


def get_rbk_cau(
    date_str: Optional[str] = None,
    limit: int = 5,
    min_cau: int = 1,
) -> dict:
    start_ms = time.perf_counter()
    target = date.fromisoformat(date_str) if date_str else date.today()
    ngay = _format_ngay(target)
    cached = _read_cache(target, limit)
    from_cache = cached is not None

    if cached:
        data = cached
    else:
        data = crawl_rbk_cau(limit, ngay)
        if not data.get("error"):
            _write_cache(target, limit, data)

    recommended, number_counts = _recommend(data.get("cau_lap", []), min_cau)
    if not recommended:
        recommended = data.get("recommended", data.get("unique_numbers", []))

    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
    return {
        "module": "rbk-cau",
        "date": target.isoformat(),
        "limit": limit,
        "min_cau": min_cau,
        "total_cau": data.get("total_cau", 0),
        "cau_tren_5ngay": data.get("cau_tren_5ngay", 0),
        "cap_so_khac_nhau": data.get("cap_so_khac_nhau", 0),
        "cap_tren_5ngay": data.get("cap_tren_5ngay", 0),
        "cap_nhieu_cau_nhat": data.get("cap_nhieu_cau_nhat", ""),
        "cau_lap": data.get("cau_lap", []),
        "unique_numbers": data.get("unique_numbers", []),
        "recommended": recommended,
        "number_counts": number_counts or data.get("number_counts", {}),
        "meta": {
            "crawl_time_ms": elapsed_ms,
            "cached": from_cache,
            "error": data.get("error"),
            "source_url": data.get("source_url"),
        },
    }


def rbk_cau_loto_matches(
    as_of_date: str,
    limit: int = 5,
    min_cau: int = 1,
) -> dict[str, dict]:
    result = get_rbk_cau(date_str=as_of_date, limit=limit, min_cau=min_cau)
    counts = result.get("number_counts") or {}
    if not counts and result.get("recommended"):
        counts = {lot: 1 for lot in result["recommended"]}
    if not counts:
        return {}

    max_count = max(counts.values()) if counts else 1
    matches: dict[str, dict] = {}
    for lot, count in counts.items():
        weight = count / max_count if max_count else 0.0
        matches[lot] = {
            "loto": lot,
            "cau_count": count,
            "max_count": max_count,
            "weight": round(weight, 3),
            "lift": round(1 + weight, 2),
        }
    return matches
