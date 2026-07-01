#!/usr/bin/env python3
"""
BACKTEST: ANTI-CONSENSUS CHO ĐỀ

Dàn 40s, 36s nuôi ĐỀ, không nuôi LÔ.
Anti-consensus: union các dàn → bỏ số đông → chọn lẻ.

Version 2: Crawl thực tế các dàn 40s từ forum tháng 6/2026
và so sánh với ensemble engine + random.
"""
import os, sys, time, random
from collections import Counter, defaultdict
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import init_pool, fetch_all
from app.prediction.constants import ALL_LOTOS
from app.prediction.features import (
    DayRecord, FeatureContext, actual_values_for_date, draw_dates_between,
)
from app.prediction.ensemble import score_ensemble

RANDOM_SEED = 42

# ===========================================================
# DÀN 40s THỰC TẾ THÁNG 6 (crawled từ forumketqua.net 27/06)
# ===========================================================

# Các dàn đang chạy cùng thời điểm (25-28/06 hoặc 26-30/06)
DAN_40S = {
    "Xuannd L11 (27-30/06)": {
        "numbers": {1,2,7,9,12,14,17,19,20,21,22,24,25,26,28,29,34,39,41,42,
                    43,46,47,48,49,52,57,59,62,67,68,70,71,75,76,82,90,92,95,97},
    },
    "No1.XS L9 (26-30/06)": {
        "numbers": {1,10,6,60,15,51,56,65,4,40,9,90,45,54,59,95,12,21,17,71,
                    26,62,67,76,23,32,28,82,37,73,78,87,34,43,39,93,48,84,89,98},
    },
    "Hanhtrinhmoi L12 (25-28/06)": {
        "numbers": {4,40,9,90,54,45,59,95,52,25,57,75,3,30,8,80,13,31,68,86,
                    14,41,19,91,64,46,69,96,24,42,29,92,74,47,79,97,22,77,2,20},
    },
    "Thuoclao6996 L13 (25-28/06)": {
        "numbers": {0,1,5,6,17,18,29,51,52,53,54,55,56,57,58,59,61,63,65,71,
                    72,73,74,75,76,78,79,81,82,83,85,87,89,90,91,92,93,95,97,98},
    },
    "emvatoi213 L11 (25-28/06)": {
        "numbers": {1,2,3,6,7,8,10,12,14,19,20,21,23,24,25,26,28,29,30,32,
                    41,42,46,52,56,62,63,64,65,67,68,71,73,75,76,79,80,82,84,85},
    },
}

# Dàn 36s K5N
DAN_36S = {
    "himle79": {
        "numbers": {1,5,10,11,12,13,14,15,16,17,18,19,21,25,31,35,41,45,
                    50,51,52,53,54,55,56,57,58,59,61,65,71,75,81,85,91,95},
    },
    "Hanhtrinhmoi 36s L9": {
        "numbers": {4,40,9,90,54,45,59,95,52,25,57,75,3,30,8,80,13,31,68,86,
                    14,41,19,91,64,46,69,96,24,42,29,92,74,47,79,97},
    },
    "Thuoclao6996 36s L10": {
        "numbers": {1,3,5,6,10,15,18,24,29,33,38,39,47,48,51,56,58,59,60,65,
                    68,74,78,79,85,86,87,88,89,92,93,94,95,96,97,98},
    },
    "danv L10 36s": {
        "numbers": {1,3,5,6,7,10,11,13,17,21,28,32,33,36,37,38,41,45,52,55,
                    59,60,61,65,67,68,70,75,83,84,85,86,91,94,95,96},
    },
}


def compute_forum_consensus(dan_dict):
    """Từ union các dàn → tính consensus score.
    
    Càng nhiều dàn chọn 1 số → consensus CAO → nên tránh (đề ít khi vào đám đông)
    """
    n_dans = len(dan_dict)
    consensus = Counter()
    for name, data in dan_dict.items():
        for n in data["numbers"]:
            consensus[n] += 1
    
    # Normalize: 0 = no dàn chọn (anti), 1 = tất cả dàn chọn (đám đông)
    scores = {}
    for v in range(100):
        c = consensus.get(v, 0)
        scores[f"{v:02d}"] = c / n_dans  # 0..1
    
    return scores


def anti_forum_score(ctx, dan_dict):
    """Chọn số ít dàn nuôi nhất.
    
    Forum anti-consensus: pick số KHÔNG nằm trong nhiều dàn.
    """
    forum_scores = compute_forum_consensus(dan_dict)
    
    # Invert: 1 - consensus = anti-consensus score
    anti = {}
    for k, v in forum_scores.items():
        anti[k] = 1.0 - v  # 0=đám đông, 1=lẻ
    
    return anti


def consensus_forum_score(ctx, dan_dict):
    """Chọn số nhiều dàn nuôi nhất (đám đông)."""
    return compute_forum_consensus(dan_dict)


# ===========================================================
# BACKTEST
# ===========================================================

def _de_dates_in_range(start, end):
    """Get de values for dates in range."""
    rows = fetch_all("""
        SELECT d.draw_date::text AS draw_date, p.last_two AS de
        FROM draws d
        JOIN prizes p ON p.draw_id = d.id AND p.slot_index = 0
        WHERE d.region = 'MB' AND d.draw_date >= %s AND d.draw_date <= %s
        ORDER BY d.draw_date
    """, (start.isoformat(), end.isoformat()))
    return [(r["draw_date"], r["de"]) for r in rows]


def run_backtest():
    start_ms = time.perf_counter()
    init_pool(min_size=1, max_size=1)
    random.seed(RANDOM_SEED)
    
    # Lấy tất cả ngày có dàn 40s: tháng 6/2026 (ngày 1-27)
    de_data = _de_dates_in_range(date(2026, 6, 1), date(2026, 6, 27))
    
    print("=" * 65)
    print("BACKTEST: ANTI-CONSENSUS CHO ĐỀ (DÀN 40s/36s)")
    print(f"Period: 01/06 → 27/06/2026 ({len(de_data)} days)")
    print("=" * 65)
    
    # ——— FORUM DÀN 40s ———
    print("\n── DÀN 40s FORUM (tháng 6) ──")
    
    for strategy_name, scorer_fn in [
        ("CONSENSUS (đám đông) ", lambda: consensus_forum_score(None, DAN_40S)),
        ("ANTI-CONSENSUS (lẻ)  ", lambda: anti_forum_score(None, DAN_40S)),
    ]:
        scores = scorer_fn()
        print(f"\n  {strategy_name}:")
        
        for top_k in (5, 10, 20, 36, 40):
            ranked = sorted(scores.items(), key=lambda x: -x[1])[:top_k]
            predicted = set(v for v, _ in ranked)
            
            hits = sum(1 for _, de in de_data if de in predicted)
            total = len(de_data)
            hr = hits / total
            rand = top_k / 100
            lift = hr / rand if rand > 0 else 0
            print(f"     Top {top_k:2d}: {hits:>2}/{total} = {hr:.1%} "
                  f"| rand {rand:.1%} | x{lift:.2f}")
    
    # ——— FORUM DÀN 36s ———
    print(f"\n── DÀN 36s FORUM (tháng 6) ──")
    
    for strategy_name, scorer_fn in [
        ("CONSENSUS (đám đông) ", lambda: consensus_forum_score(None, DAN_36S)),
        ("ANTI-CONSENSUS (lẻ)  ", lambda: anti_forum_score(None, DAN_36S)),
    ]:
        scores = scorer_fn()
        print(f"\n  {strategy_name}:")
        
        for top_k in (5, 10, 20, 36):
            ranked = sorted(scores.items(), key=lambda x: -x[1])[:top_k]
            predicted = set(v for v, _ in ranked)
            
            hits = sum(1 for _, de in de_data if de in predicted)
            total = len(de_data)
            hr = hits / total
            rand = top_k / 100
            lift = hr / rand if rand > 0 else 0
            print(f"     Top {top_k:2d}: {hits:>2}/{total} = {hr:.1%} "
                  f"| rand {rand:.1%} | x{lift:.2f}")
    
    # ——— SO SÁNH: số nào cả 5 dàn 40s cùng chọn vs không dàn nào chọn ———
    print(f"\n── SO SÁNH ĐỀ THỰC TẾ vs CONSENSUS 40s ──")
    
    forum_scores = compute_forum_consensus(DAN_40S)
    de_count = Counter(de for _, de in de_data)
    
    print(f"\n  {'Consensus level':<25} {'Số lượng':>8} {'Đề trúng':>8} {'Hit rate':>8}")
    print("  " + "-" * 50)
    
    for level, pct_threshold, label in [
        (0.8, 0.8, ">=80% dàn (đám đông)"),
        (0.6, 0.6, ">=60% dàn"),
        (0.4, 0.4, ">=40% dàn"),
        (0.2, 0.2, ">=20% dàn"),
        (0.0, 0.0, ">0% dàn"),
    ]:
        nums_in_level = {k for k, v in forum_scores.items() if v >= pct_threshold and k != "0.00"}
        hits_in_level = sum(1 for _, de in de_data if de in nums_in_level)
        total_de = len(de_data)
        pct = hits_in_level / total_de * 100 if total_de else 0
        print(f"  {label:<25} {len(nums_in_level):>8} {hits_in_level:>8} {pct:>7.1f}%")
    
    # Numbers NOT in any dàn
    nums_no_dan = {f"{v:02d}" for v in range(100)} - set(forum_scores.keys())
    # Actually all numbers are in forum_scores (0 means no dàn picked it)
    nums_no_dan = {k for k, v in forum_scores.items() if v == 0.0}
    hits_no_dan = sum(1 for _, de in de_data if de in nums_no_dan)
    print(f"  {'Không dàn nào chọn':<25} {len(nums_no_dan):>8} {hits_no_dan:>8} {hits_no_dan/len(de_data)*100:>7.1f}%")
    
    # Phân tích cụ thể từng ngày
    print(f"\n── PHÂN TÍCH TỪNG NGÀY THÁNG 6 ──")
    print(f"  {'Ngày':<6} {'Đề':>5} {'Consensus':>10} {'Số dàn chọn':>12} {'Trong dàn 40s?':>14}")
    print("  " + "-" * 55)
    for dt_str, de in de_data:
        c = int(forum_scores.get(de, 0) * 100)
        n_dan = round(forum_scores.get(de, 0) * len(DAN_40S))
        in_40s = "CÓ ✓" if forum_scores.get(de, 0) > 0 else "KHÔNG ✗"
        bar = "█" * (c // 10)
        print(f"  {dt_str[-5:]:<6} {de:>5}  {c:>3}% {bar:<10} {n_dan:>3}/{len(DAN_40S):<5} {in_40s:<14}")
    
    elapsed = int((time.perf_counter() - start_ms) * 1000)
    print(f"\n⏱ {elapsed}ms")


if __name__ == "__main__":
    run_backtest()
