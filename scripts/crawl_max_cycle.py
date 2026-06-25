#!/usr/bin/env python3
"""Crawl max gan data from mketqua.net/loto-gan and save to JSON."""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "app" / "data" / "max_cycle_history.json"
URL = "https://mketqua.net/loto-gan"
SOURCE_URL = URL

_DATE_RE = re.compile(r"(\d{2})-(\d{2})-(\d{4})")


def _parse_vn_date(text: str) -> Optional[str]:
    m = _DATE_RE.search(text.strip())
    if not m:
        return None
    day, month, year = m.group(1), m.group(2), m.group(3)
    return f"{year}-{month}-{day}"


def _parse_tooltip_dates(title: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse 'Từ 10-07-2018 đến 08-08-2018' -> (start, end) ISO dates."""
    if not title:
        return None, None
    parts = title.split("đến")
    if len(parts) != 2:
        return None, None
    return _parse_vn_date(parts[0].replace("Từ", "")), _parse_vn_date(parts[1])


def parse_max_cycle_html(html: str) -> dict[str, dict]:
    soup = BeautifulSoup(html, "html.parser")
    data: dict[str, dict] = {}

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        i = 0
        while i < len(rows):
            row = rows[i]
            cells = row.find_all("td")
            if not cells:
                i += 1
                continue
            label = cells[0].get_text(strip=True)
            if label != "Bộ số":
                i += 1
                continue
            numbers = []
            for cell in cells[1:]:
                b = cell.find("b")
                num = (b.get_text(strip=True) if b else cell.get_text(strip=True))
                if re.fullmatch(r"\d{2}", num):
                    numbers.append(num)

            if i + 1 >= len(rows):
                break
            max_row = rows[i + 1]
            max_cells = max_row.find_all("td")
            if not max_cells or max_cells[0].get_text(strip=True) != "Max gan":
                i += 1
                continue

            for num, cell in zip(numbers, max_cells[1:]):
                span = cell.find("span", class_="target_tooltip")
                if span is None:
                    continue
                try:
                    max_gap_days = int(span.get_text(strip=True))
                except ValueError:
                    continue
                title = span.get("data-original-title") or span.get("title") or ""
                start, end = _parse_tooltip_dates(title)
                data[num] = {
                    "max_gap_days": max_gap_days,
                    "max_gap_start": start,
                    "max_gap_end": end,
                    "source_url": SOURCE_URL,
                }
            i += 2

    return data


def crawl(url: str = URL, output: Path = OUTPUT) -> dict[str, dict]:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    data = parse_max_cycle_html(html)
    if len(data) < 100:
        raise RuntimeError(f"Expected 100 numbers, got {len(data)}")

    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source_url": SOURCE_URL,
        "crawled_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "numbers": data,
    }
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Crawled {len(data)} numbers -> {output}")
    return data


def main() -> int:
    try:
        crawl()
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
