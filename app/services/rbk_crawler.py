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
from app.db import fetch_all
from app.prediction.constants import TARGET_LOTO
from app.prediction.features import actual_values_for_date, previous_draw_date
from app.utils.http_util import obtain_content

logger = logging.getLogger(__name__)

CACHE_DIR = Path("/tmp/app_cache")
CACHE_TTL = timedelta(days=1)

NET_CAU_URL = (
    "https://rongbachkim.net/soicau.html?submit=1&setmode=full&exactlimit=0"
    "&limit={limit}&ngay={ngay}&nhay={nhay}&lon={lon}"
)


def _format_ngay(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _cache_path(d: date, limit: int, lon: int = 1) -> Path:
    return CACHE_DIR / f"{d.isoformat()}_{limit}_{lon}.json"


def _read_cache(d: date, limit: int, lon: int = 1, allow_stale: bool = False) -> Optional[dict]:
    path = _cache_path(d, limit, lon)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not allow_stale:
            cached_at = datetime.fromisoformat(payload["cached_at"])
            if datetime.now() - cached_at > CACHE_TTL:
                return None
        return payload["data"]
    except (json.JSONDecodeError, KeyError, ValueError):
        logger.exception("_read_cache failed for path: %s", path)
        return None


def _write_cache(d: date, limit: int, data: dict, lon: int = 1) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(d, limit, lon)
    path.write_text(
        json.dumps({"cached_at": datetime.now().isoformat(), "data": data}, ensure_ascii=False),
        encoding="utf-8",
    )


def _build_url(limit: int, ngay: str, lon: int = 1, nhay: int = 1) -> str:
    from urllib.parse import quote
    ngay_encoded = quote(ngay, safe="")
    return NET_CAU_URL.format(limit=limit, ngay=ngay_encoded, nhay=nhay, lon=lon)


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


def crawl_rbk_cau(limit: int, ngay: str, lon: int = 1, nhay: int = 1) -> dict:
    url = _build_url(limit, ngay, lon, nhay)
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
    lon: int = 1,
    nhay: int = 1,
    allow_stale_cache: bool = False,
    crawl_if_missing: bool = True,
) -> dict:
    start_ms = time.perf_counter()
    target = date.fromisoformat(date_str) if date_str else date.today()
    ngay = _format_ngay(target)
    cached = _read_cache(target, limit, lon=lon, allow_stale=allow_stale_cache)
    from_cache = cached is not None

    if cached:
        data = cached
    elif crawl_if_missing:
        data = crawl_rbk_cau(limit, ngay, lon, nhay)
        if not data.get("error"):
            _write_cache(target, limit, data, lon=lon)
    else:
        data = {
            "error": "cache_miss",
            "total_cau": 0,
            "cau_lap": [],
            "unique_numbers": [],
            "recommended": [],
            "number_counts": {},
        }

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
    lon: int = 1,
    nhay: int = 1,
) -> dict[str, dict]:
    result = get_rbk_cau(date_str=as_of_date, limit=limit, min_cau=min_cau, lon=lon, nhay=nhay)
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


BACKTEST_LIMITS = (1, 3, 5, 7, 9)


def run_rbk_cau_backtest(days: int = 30) -> dict:
    start_ms = time.perf_counter()
    rows = fetch_all(
        """
        SELECT draw_date::text AS draw_date
        FROM draws
        WHERE region = 'MB'
        ORDER BY draw_date DESC
        LIMIT %s
        """,
        (days,),
    )
    target_dates = sorted(row["draw_date"] for row in rows)
    if not target_dates:
        return {
            "module": "rbk-cau-backtest",
            "days_requested": days,
            "days_evaluated": 0,
            "limits": [],
            "meta": {"query_time_ms": 0, "error": "no_draw_data"},
        }

    limit_stats: dict[int, dict] = {
        lim: {
            "limit": lim,
            "days_evaluated": 0,
            "days_skipped": 0,
            "hit_days": 0,
            "total_recall": 0.0,
            "total_overlap": 0,
            "total_recommended": 0,
            "total_actual": 0,
        }
        for lim in BACKTEST_LIMITS
    }

    for target_date in target_dates:
        target_dt = date.fromisoformat(target_date)
        as_of = previous_draw_date(target_dt)
        if not as_of:
            continue
        actual = set(actual_values_for_date(target_dt, TARGET_LOTO))
        if not actual:
            continue

        for lim in BACKTEST_LIMITS:
            result = get_rbk_cau(
                date_str=as_of.isoformat(),
                limit=lim,
                lon=1,
                allow_stale_cache=True,
                crawl_if_missing=True,
            )
            if result.get("meta", {}).get("error"):
                limit_stats[lim]["days_skipped"] += 1
                continue

            recommended = set(result.get("recommended", []))
            overlap = len(recommended & actual)
            stats = limit_stats[lim]
            stats["days_evaluated"] += 1
            stats["total_overlap"] += overlap
            stats["total_recommended"] += len(recommended)
            stats["total_actual"] += len(actual)
            stats["total_recall"] += overlap / len(actual)
            if overlap > 0:
                stats["hit_days"] += 1

    limits_out: list[dict] = []
    best_limit: Optional[int] = None
    best_score = -1.0
    for lim in BACKTEST_LIMITS:
        stats = limit_stats[lim]
        evaluated = stats["days_evaluated"]
        hit_rate = stats["hit_days"] / evaluated if evaluated else 0.0
        avg_recall = stats["total_recall"] / evaluated if evaluated else 0.0
        avg_recommended = stats["total_recommended"] / evaluated if evaluated else 0.0
        avg_overlap = stats["total_overlap"] / evaluated if evaluated else 0.0
        row = {
            "limit": lim,
            "days_evaluated": evaluated,
            "days_skipped": stats["days_skipped"],
            "hit_rate": round(hit_rate, 4),
            "avg_recall": round(avg_recall, 4),
            "avg_overlap": round(avg_overlap, 2),
            "avg_recommended_count": round(avg_recommended, 1),
        }
        limits_out.append(row)
        score = hit_rate * 0.4 + avg_recall * 0.6
        if evaluated > 0 and score > best_score:
            best_score = score
            best_limit = lim

    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
    return {
        "module": "rbk-cau-backtest",
        "period_from": target_dates[0],
        "period_to": target_dates[-1],
        "days_requested": days,
        "days_evaluated": len(target_dates),
        "recommended_limit": best_limit,
        "limits": limits_out,
        "meta": {
            "query_time_ms": elapsed_ms,
            "note": "cau as_of_date predicts next draw; stale cache allowed for historical dates",
        },
    }
