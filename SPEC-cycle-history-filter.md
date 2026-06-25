# SPEC: Chu kỳ 1 con lô — Max Cycle History & Gap Ratio Filter

## Mục tiêu

Bổ sung filter dựa trên **chu kỳ lịch sử (max cycle)** của từng con lô 00-99 để phát hiện số sắp đến hạn về. Hiện tại engine chỉ có:
- `max-cycle` filter dùng pct_of_max từ DB (matched=0 hôm qua vì threshold quá cao)
- `gap-hot` filter dùng current_gap thuần túy

Cần thêm: **cycle-history filter** dùng max cycle thực tế từ lịch sử (lấy từ mketqua.net), so với current gap để tính gap_ratio = current_gap / max_cycle_history.

## Source: mketqua.net/loto-gan

Trang cung cấp **Max gan** cho từng số 00-99. Ví dụ:
- 55: max gan = 42 ngày
- 80: max gan = 40 ngày
- 39: max gan = 38 ngày
- 26, 73, 74: max gan = 36 ngày

Đây là số ngày gan tối đa trong **toàn bộ lịch sử** (không chỉ trong DB hiện tại).

## Dữ liệu cần crawl

### Bảng max_cycle_history (static table hoặc JSON file)

| number | max_gap_days | max_gap_start | max_gap_end | source_url |
|--------|-------------|---------------|-------------|------------|
| 00 | 28 | 2018-07-10 | 2018-08-08 | mketqua.net |
| 01 | 24 | ... | ... | mketqua.net |
| ... | ... | ... | ... | ... |
| 99 | 26 | ... | ... | mketqua.net |

**Toàn bộ 100 số, lưu dưới dạng JSON** trong `app/data/max_cycle_history.json`.

### Crawl script

Tạo `scripts/crawl_max_cycle.py`:

```python
#!/usr/bin/env python3
"""Crawl max gan data from mketqua.net/loto-gan and save to JSON."""

import json, re, sys
from urllib.request import Request, urlopen

URL = "https://mketqua.net/loto-gan"

def crawl():
    req = Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=15) as r:
        html = r.read().decode("utf-8", errors="replace")
    
    # Parse the max gan table
    # Format in HTML: table rows with number and max_gan columns
    # Pattern: | Bo so | XX | max_gan = YY |
    
    data = {}
    # TODO: parse HTML to extract {number: max_gap_days}
    # The table has columns: Bộ số | 00 | 01 | 02 | ... and Max gan | 28 | 24 | ...
    
    with open("app/data/max_cycle_history.json", "w") as f:
        json.dump(data, f, indent=2)
    
    print(f"Crawled {len(data)} numbers")
    return data

if __name__ == "__main__":
    crawl()
```

**Lưu ý parse:** Trang mketqua.net/loto-gan có bảng dạng:
```
| Bộ số | 00 | 01 | 02 | ... | 19 |
| Max gan | 28 | 24 | 22 | ... | 20 |
| Bộ số | 20 | 21 | ... | 39 |
| Max gan | 24 | 28 | ... | 38 |
...
```

Cần parse 5 hàng "Max gan" tương ứng 5 nhóm: 00-19, 20-39, 40-59, 60-79, 80-99.

**Chạy định kỳ:** Mỗi tháng 1 lần (max cycle history hiếm khi thay đổi).

## Logic filter mới

### Filter name: `cycle-history`

### Trigger conditions

Một số được filter matched nếu:
- `current_gap >= max_cycle_history * 0.50` (đã đi được 50% chu kỳ lịch sử)
- VÀ `current_gap >= 10` (ít nhất 10 ngày gan để tránh nhiễu)

### Score contribution

```
gap_ratio = current_gap / max_cycle_history (clamped to [0.5, 1.0])
contribution = gap_ratio * 0.5 (max 0.5 pts)
```

| Gap ratio | % chu kỳ | Contribution |
|-----------|----------|-------------|
| 0.50 | 50% | 0.25 |
| 0.60 | 60% | 0.30 |
| 0.75 | 75% | 0.38 |
| 0.90+ | 90%+ | 0.45-0.50 |

### Place trong filter pipeline

Trong `_loto_filter_defs()`, thêm sau `gap-hot` filter:

```python
{
    "key": "cycle-history",
    "min_ratio": 0.50,
    "fn": lambda: _cycle_history_matches(as_of_date),
}
```

### Hàm _cycle_history_matches

```python
def _cycle_history_matches(as_of_date: str) -> list[FilterMatch]:
    """
    Match numbers whose current gap >= 50% of historical max cycle.
    Uses max_cycle_history.json (crawled from mketqua.net).
    """
    # 1. Load max_cycle_history
    # 2. Get current_gap for each number from DB
    # 3. Calculate gap_ratio = current_gap / max_gap
    # 4. If gap_ratio >= 0.50 and current_gap >= 10 → add match
```

Detail dict trả về:
```python
{
    "gap_ratio": round(gap_ratio, 3),
    "current_gap": current_gap,
    "max_gap": max_gap,
    "lift": round(1.0 + gap_ratio * 0.5, 3),  # lift = 1.25-1.50x
}
```

### Score contribution

```python
# Trong _score_contribution():
if filter_key == "cycle-history":
    gap_ratio = float(detail.get("gap_ratio", 0.5))
    return min(gap_ratio * 0.5, 0.5)  # max 0.5
```

## Điều chỉnh max-cycle hiện tại

Giảm `min_pct` từ 55 → **40%** để filter này có matched:

```python
# Trong _loto_filter_defs():
{"key": "max-cycle", "min_pct": 40, "fn": lambda: _max_cycle_matches()},
```

## File cần thay đổi

| File | Thay đổi |
|------|---------|
| `app/data/max_cycle_history.json` | **Mới** — dữ liệu crawl từ mketqua (100 số) |
| `scripts/crawl_max_cycle.py` | **Mới** — crawler script |
| `app/services/candidate_service.py` | Thêm `_cycle_history_matches()`, thêm filter def, thêm score contribution, giảm max-cycle min_pct |
| `.gitignore` | Thêm `app/data/` nếu chưa có |

## Crawl + Test Steps

1. Chạy `scripts/crawl_max_cycle.py` → tạo `app/data/max_cycle_history.json`
2. Verify file có đủ 100 số với max_gap_days
3. Chạy `build_candidates(target_date='today')` → kiểm tra `cycle-history` filter matched
4. Check score breakdown cho các số có gap_ratio cao
5. Nếu OK → commit

## Edge cases

- Số chưa từng về (max_gap = ∞): skip, không matched
- Số current_gap = 0 (về hôm qua): skip
- JSON file không tồn tại: filter trả về [] (graceful degradation)
- DB empty: filter trả về []
