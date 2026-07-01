#!/usr/bin/env python3
"""Sync XSMB data from xosodaiphat.com to database.
Runs before xsmb_daily_report.py to ensure latest draws are available."""

import os
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
VENV_PYTHON = os.path.join(PROJECT_ROOT, ".venv", "bin", "python3")
if os.path.exists(VENV_PYTHON) and sys.executable != VENV_PYTHON:
    os.execv(VENV_PYTHON, [VENV_PYTHON] + sys.argv)

sys.path.insert(0, PROJECT_ROOT)

from datetime import date, timedelta
from app.config import settings
from app.db import execute, fetch_all, init_pool
from psycopg.rows import tuple_row
import psycopg


def _fetch_page(url: str) -> str:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
    with urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", errors="replace")


def _parse_xosodaiphat(html: str) -> list[dict]:
    """Parse prizes from xosodaiphat.com result page HTML."""
    prizes = []
    
    # Find the results table - look for Đặc biệt/DB
    # Pattern: (DB|G[1-7]) + ... + number digits
    lines = html.split("\n")
    
    prize_order = [
        ("DB", 0), ("G1", 1), ("G2", 2), ("G2", 3),
        ("G3", 4), ("G3", 5), ("G3", 6), ("G3", 7), ("G3", 8), ("G3", 9),
        ("G4", 10), ("G4", 11), ("G4", 12), ("G4", 13),
        ("G5", 14), ("G5", 15), ("G5", 16), ("G5", 17), ("G5", 18), ("G5", 19),
        ("G6", 20), ("G6", 21), ("G6", 22),
        ("G7", 23), ("G7", 24), ("G7", 25), ("G7", 26),
    ]
    
    # Try structured table approach
    table_pattern = re.compile(
        r'<td[^>]*>\s*<strong>\s*(Đặc biệt|Giải nhất|Giải nhì|Giải ba|Giải tư|Giải năm|Giải sáu|Giải bảy)\s*</strong>'
    )
    
    # Simpler: find all 5-digit numbers in the content near prize labels
    # The HTML from xosodaiphat.com has structure: | Giải | Kết quả | with numbers
    # Find all rows with digits

    # Try to find numbers in table cells
    # Pattern: look for | (level) | (number) |
    all_numbers = re.findall(r'\|\s*\*{0,2}(?:\d{5}|\d{4}|\d{3}|\d{2})\*{0,2}\s*\|', html)
    
    # Better approach: extract from markdown table
    # The web_extract gives us markdown tables
    # Look for patterns like | DB | 50437 |
    lines = html.split('\n')
    found_prizes = []
    for line in lines:
        line = line.strip()
        # Match markdown table row: | DB | 50437 | or | **Đặc biệt** | **50437** |
        m = re.match(r'\|\s*\*?(Đặc biệt|DB|Giải nhất|G1|Giải nhì|G2|Giải ba|G3|Giải tư|G4|Giải năm|G5|Giải sáu|G6|Giải bảy|G7)\*?\s*\|\s*\*?(\d{2,5})\*?\s*\|', line)
        if m:
            label = m.group(1)
            number = m.group(2)
            found_prizes.append((label, number))
    
    return found_prizes


def _extract_full_result_date(url_date: str) -> dict:
    """Get full prize list for a specific date from xosodaiphat.com."""
    url = f"https://xosodaiphat.com/xsmb-{url_date}.html"
    html = _fetch_page(url)
    
    prizes = _parse_xosodaiphat(html)
    return {"prizes": prizes}


def sync_missing_draws(up_to: date = None) -> list[date]:
    """Check for missing MB draws and sync them from xosodaiphat.com."""
    if up_to is None:
        up_to = date.today()
    
    # Find latest MB draw
    rows = fetch_all(
        "SELECT MAX(draw_date)::text AS d FROM draws WHERE region='MB'"
    )
    if not rows or not rows[0].get("d"):
        return []
    
    latest = date.fromisoformat(rows[0]["d"])
    missing_dates = []
    
    # Check weekday dates between latest+1 and up_to
    check = latest + timedelta(days=1)
    while check <= up_to:
        if check.weekday() != 6:  # Skip Sunday (no draw)
            # Check if exists
            existing = fetch_all(
                "SELECT id FROM draws WHERE draw_date=%s AND region='MB'",
                (check.isoformat(),)
            )
            if not existing:
                missing_dates.append(check)
        check += timedelta(days=1)
    
    if not missing_dates:
        return missing_dates  # Empty list - nothing to sync
    
    conn = psycopg.connect(settings.database_url, row_factory=tuple_row)
    
    for d in missing_dates:
        url_date = d.strftime("%d-%m-%Y")
        print(f"Fetching {d} from xosodaiphat.com...")
        
        url = f"https://xosodaiphat.com/xsmb-{url_date}.html"
        try:
            html = _fetch_page(url)
            prizes = _parse_xosodaiphat(html)
            
            # Validate we have DB (at minimum)
            if not prizes:
                print(f"  Could not parse any prizes for {d}")
                continue
            
            # Insert draw
            station = ""
            # Determine station by weekday
            wd_stations = {0: "Hà Nội", 1: "Quảng Ninh", 2: "Bắc Ninh", 
                          3: "Hà Nội", 4: "Hải Phòng", 5: "Nam Định", 6: "Thái Bình"}
            station = wd_stations.get(d.weekday(), "Hà Nội")
            
            result = conn.execute('''INSERT INTO draws (draw_date, region, station, label, source, created_at, updated_at)
                VALUES (%s, 'MB', %s, %s, 'web', NOW(), NOW()) RETURNING id''',
                (d.isoformat(), station, 'XSMB ' + str(d)))
            draw_id = result.fetchone()[0]
            
            # Map labels to levels
            label_map = {
                'DB': 'DB', 'Đặc biệt': 'DB',
                'G1': 'G1', 'Giải nhất': 'G1',
                'G2': 'G2', 'Giải nhì': 'G2',
                'G3': 'G3', 'Giải ba': 'G3',
                'G4': 'G4', 'Giải tư': 'G4',
                'G5': 'G5', 'Giải năm': 'G5',
                'G6': 'G6', 'Giải sáu': 'G6',
                'G7': 'G7', 'Giải bảy': 'G7',
            }
            
            slot_map = {
                'DB': 0, 'G1': 1,
            }
            g2_slot = 2
            g3_slot = 4
            g4_slot = 10
            g5_slot = 14
            g6_slot = 20
            g7_slot = 23
            
            current_slots = {
                'G2': 2, 'G3': 4, 'G4': 10, 'G5': 14, 'G6': 20, 'G7': 23
            }
            
            from collections import defaultdict
            # Group by level
            by_level = defaultdict(list)
            for label, number in prizes:
                level = label_map.get(label, label)
                by_level[level].append(number)
            
            slot = 0
            inserted = 0
            for level in ['DB', 'G1', 'G2', 'G3', 'G4', 'G5', 'G6', 'G7']:
                nums = by_level.get(level, [])
                for num in nums:
                    last_two = num[-2:]
                    first_digit = num[-2]
                    last_digit = num[-1]
                    conn.execute('''INSERT INTO prizes (draw_id, slot_index, prize_level, prize_order, number, last_two, first_digit, last_digit)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)''',
                        (draw_id, slot, level, 0, num, last_two, first_digit, last_digit))
                    inserted += 1
                    slot += 1
            
            print(f"  Inserted {inserted} prizes (draw_id={draw_id})")
            
        except Exception as e:
            print(f"  Error syncing {d}: {e}")
            continue
    
    conn.commit()
    conn.close()
    
    return missing_dates


def main():
    init_pool(min_size=1, max_size=1)
    
    today = date.today()
    synced = sync_missing_draws(today)
    
    if synced:
        for d in synced:
            print(f"✅ Synced: {d}")
    else:
        print("✅ All MB draws up to date")


if __name__ == "__main__":
    main()
