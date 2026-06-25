# SPEC: Conditional Frequency & Date-based Filters — Tận dụng edge từ dữ liệu có điều kiện

## Lý do

Backtest 51 ngày cho thấy:
- Engine recall: 23.05% vs Random: 20.89% — edge chỉ 1.10x
- Filter `conditional-frequency` hiện tại dùng `min_lift=1.05` — matched quá loãng
- Mketqua.net/giai-db-ngay-mai có edge thực sự nhờ conditional probability (e.g. đề 36 → 17 với 4.5x lift)

Mục tiêu: Tận dụng **3 loại conditional signals** có edge cao hơn random đáng kể.

## 1. Tách conditional-frequency filter

### Hiện tại

```python
# Trong _loto_filter_defs():
{
    "key": "conditional-frequency",
    "min_lift": 1.05,  # quá thấp — matched gần như mọi số
    "fn": lambda: _conditional_frequency_filter_matches(yesterday_de, weekday),
}
```

### Thay bằng 2 filter riêng

#### Filter A: `cond-freq-loto` (cho lô)

```python
{
    "key": "cond-freq-loto",
    "min_lift": 2.0,
    "min_occ": 3,
    "fn": lambda: _cond_freq_loto_matches(yesterday_de),
}
```

- `min_lift=2.0`: chỉ lấy số có lift >= 2x so với random
- `min_occ=3`: ít nhất 3 lần xuất hiện trong lịch sử (tránh noise)
- Score contribution: `min((lift - 1) * 0.5, 0.6)` — tối đa 0.6 pts

#### Filter B: `cond-freq-de` (cho đề)

```python
{
    "key": "cond-freq-de",
    "min_lift": 3.0,
    "min_occ": 2,
    "fn": lambda: _cond_freq_de_matches(yesterday_de),
}
```

- `min_lift=3.0`: chỉ lấy số có lift >= 3x (edge mketqua-style)
- Score contribution: `min((lift - 1) * 0.3, 0.7)` — tối đa 0.7 pts

### Hàm mới

```python
def _cond_freq_loto_matches(
    yesterday_de: str,
    min_lift: float = 2.0,
    min_occ: int = 3,
) -> list[FilterMatch]:
    """
    Match lô có conditional frequency cao khi đề hôm qua là yesterday_de.
    """
    result = get_conditional_frequency(
        db_loto=yesterday_de,
        target_weekday=None,
        min_occ=min_occ,
        limit=20,
        sort="lift",
    )
    matches: list[FilterMatch] = []
    for row in result["loto_frequency"]:
        if row["lift"] < min_lift:
            continue
        reason = (
            f"cond-freq-loto: sau đề {yesterday_de} loto {row['loto']} "
            f"về {row['occurrences']}/{result['total_samples']} lần "
            f"(lift {row['lift']:.2f}x)"
        )
        matches.append((row["loto"], reason, {
            "lift": round(row["lift"], 3),
            "occurrences": row["occurrences"],
            "total_samples": result["total_samples"],
        }))
    return matches


def _cond_freq_de_matches(
    yesterday_de: str,
    min_lift: float = 3.0,
    min_occ: int = 2,
) -> list[FilterMatch]:
    """
    Match đề có conditional frequency cao khi đề hôm qua là yesterday_de.
    """
    result = get_conditional_frequency(
        db_loto=yesterday_de,
        target_weekday=None,
        min_occ=min_occ,
        limit=20,
        sort="lift",
    )
    matches: list[FilterMatch] = []
    for row in result["loto_frequency"]:
        if row["lift"] < min_lift:
            continue
        reason = (
            f"cond-freq-de: sau đề {yesterday_de} đề {row['loto']} "
            f"về {row['occurrences']}/{result['total_samples']} lần "
            f"(lift {row['lift']:.2f}x)"
        )
        matches.append((row["loto"], reason, {
            "lift": round(row["lift"], 3),
            "occurrences": row["occurrences"],
            "total_samples": result["total_samples"],
        }))
    return matches
```

### Xóa filter cũ

```python
# XÓA dòng này khỏi _loto_filter_defs():
# {"key": "conditional-frequency", "min_lift": 1.05, "fn": lambda: ...},
```

## 2. Thêm filter `same-date` (ngày trùng trong năm)

### Ý tưởng

Mketqua có bảng "Thống kê giải ĐB ngày 23-06 hàng năm" — cho thấy kết quả cùng ngày qua các năm (2000-2025). Ví dụ:
- 23/06/2025: 52157 → đề 57
- 23/06/2024: 28501 → đề 01
- ...

Nếu hôm nay là 26/06, thì những năm trước ngày 26/06 về con gì? Đây là **date-based frequency** — có edge vì lịch sử lặp lại.

### Filter name: `same-date`

```python
{
    "key": "same-date",
    "min_occ": 1,
    "fn": lambda: _same_date_matches(target_date),
}
```

### Hàm _same_date_matches

```python
def _same_date_matches(
    target_date: str,
    min_occ: int = 1,
) -> list[FilterMatch]:
    """
    Match loto dựa trên kết quả cùng ngày trong các năm trước.
    Ví dụ: target_date=2026-06-26, lấy kết quả các ngày 26/06 từ 2000-2025.
    """
    dt = date.fromisoformat(target_date)
    month_day = (dt.month, dt.day)
    
    rows = fetch_all("""
        SELECT p.last_two AS loto, COUNT(*) AS cnt
        FROM draws d
        JOIN prizes p ON p.draw_id = d.id
        WHERE d.region = 'MB'
          AND EXTRACT(MONTH FROM d.draw_date) = %s
          AND EXTRACT(DAY FROM d.draw_date) = %s
          AND d.draw_date < %s::date
          AND p.slot_index = 0  -- chỉ lấy giải ĐB
        GROUP BY p.last_two
        ORDER BY cnt DESC
    """, (month_day[0], month_day[1], target_date))
    
    if not rows:
        return []
    
    total = sum(r["cnt"] for r in rows)
    matches: list[FilterMatch] = []
    for row in rows:
        lift = (row["cnt"] / total) / (1 / 100)  # vs random 1%
        if lift < 1.5:
            continue
        reason = (
            f"same-date: ngày {dt.month}/{dt.day} lịch sử "
            f"{row['loto']} về {row['cnt']}/{total} lần (lift {lift:.1f}x)"
        )
        matches.append((row["loto"], reason, {
            "lift": round(lift, 2),
            "occurrences": row["cnt"],
            "total_years": total,
        }))
    return matches
```

### Score contribution

```python
if filter_key == "same-date":
    lift = float(detail.get("lift", 1))
    return min((lift - 1) * 0.3, 0.5)  # max 0.5 pts
```

## 3. Thêm filter `de-lag1-cond` cho Đề

### Ý tưởng

Mketqua thống kê "khi đề 36 thì hôm sau đề gì" — edge rất cao (17 có 4.5x lift). Engine hiện có `de-lag1` nhưng chỉ dùng frequency đơn thuần.

### Filter name: `de-cond-prev` (cho đề)

```python
{
    "key": "de-cond-prev",
    "fn": lambda: _de_cond_prev_matches(yesterday_de),
}
```

### Hàm

```python
def _de_cond_prev_matches(yesterday_de: str) -> list[FilterMatch]:
    """Đề hôm nay = ? biết đề hôm qua = yesterday_de."""
    if not yesterday_de:
        return []
    
    result = get_conditional_frequency(
        db_loto=yesterday_de,
        target_weekday=None,
        min_occ=2,
        limit=10,
        sort="lift",
    )
    
    matches: list[FilterMatch] = []
    for row in result["loto_frequency"]:
        if row["lift"] < 2.0:  # thấp hơn 2x thì bỏ
            continue
        reason = (
            f"de-cond-prev: đề {yesterday_de}→{row['loto']} "
            f"{row['occurrences']} lần (lift {row['lift']:.1f}x)"
        )
        matches.append((row["loto"], reason, {
            "lift": round(row["lift"], 3),
            "occurrences": row["occurrences"],
        }))
    return matches
```

### Score contribution

```python
if filter_key == "de-cond-prev":
    lift = float(detail.get("lift", 1))
    return min((lift - 1) * 0.5, 0.8)  # max 0.8 — ưu tiên cao cho đề
```

## 4. Thêm vào DE filter pipeline

Hiện tại `_de_filter_defs()` chưa có `de-cond-prev`:

```python
# Thêm vào _de_filter_defs() sau de-lag1:
{
    "key": "de-cond-prev",
    "fn": lambda: _de_cond_prev_matches(yesterday_de),
},
```

## File cần thay đổi

| File | Thay đổi |
|------|---------|
| `app/services/candidate_service.py` | Thêm 3 hàm mới, thêm 3 filter defs, thêm 3 score contributions, xóa conditional-frequency cũ |
| | Sửa `_de_filter_defs()` thêm `de-cond-prev` |

## Test steps

1. Chạy `build_candidates(target_date='2026-06-26', target='loto', ...)` 
2. Kiểm tra `cond-freq-loto` matched ≠ 0
3. Kiểm tra `same-date` matched ≠ 0 (vì 26/06 có lịch sử các năm)
4. Chạy `build_candidates(target_date='2026-06-26', target='de', ...)`
5. Kiểm tra `de-cond-prev` matched ≠ 0 (vì đề hôm qua 16 → conditional)
6. Verify score breakdown hợp lý

## Edge cases

- Ngày target không có lịch sử (VD: 29/02): `same-date` trả về []
- yesterday_de là số lạ (ít xuất hiện): `cond-freq-*` có thể 0 matched — OK
- DB không có dữ liệu đủ sâu cho conditional: vẫn chạy, chỉ ít matched
