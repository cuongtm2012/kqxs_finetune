# Spec Delta: Expert Performance API

## ADDED Requirements

### REQ-EP-001: GET performance by period

```
GET /forum/experts/performance?period=2026-06
```

Response:

```json
{
  "period_label": "2026-06",
  "period_start": "2026-06-01",
  "period_end": "2026-06-30",
  "computed_at": "2026-07-01T12:00:00Z",
  "users": {
    "nhcsxh": {
      "btl": {"hits": 6, "total": 8, "win_rate": 0.75, "rate_pct": 75.0},
      "stl": {"hits": 4, "total": 8, "win_rate": 0.5, "rate_pct": 50.0}
    },
    "T98": {
      "stl": {"hits": 12, "total": 15, "win_rate": 0.8, "rate_pct": 80.0}
    }
  },
  "row_count": 25
}
```

**Scenario: Period chưa seed**
- THEN `users = {}`, `row_count = 0` (HTTP 200, không 404)

---

### REQ-EP-002: POST refresh performance

```
POST /forum/experts/performance/refresh?period=2026-06&write_pick_results=true
```

Recompute từ `forum_user_picks` + draws, upsert `expert_win_rates`.

Response:

```json
{
  "ok": true,
  "period_label": "2026-06",
  "rows_upserted": 25,
  "pick_results_written": 142,
  "skipped_no_draw": 3
}
```

**Scenario: Dry-run (optional query `dry_run=true`)**
- THEN trả stats, không ghi DB

---

### REQ-EP-003: `live_experts.performance` từ DB

`GET /forum/recommendations` → `live_experts[]` SHALL populate `performance` từ `expert_win_rates`:

```json
{
  "user": "T98",
  "pick_type": "stl",
  "numbers": ["68", "86"],
  "weight": 0.95,
  "performance": {
    "hits": 12,
    "total": 15,
    "rate_pct": 80.0
  }
}
```

Lookup order:
1. `(user, pick_type, period)` — period mặc định `2026-06` cho đến khi `rolling_90d` đủ mẫu
2. Fallback `(user, default, period)` nếu không có pick_type cụ thể
3. Fallback `run_backtest()` in-memory
4. `null` → UI `—`

**Scenario: Extension tab Đề xuất**
- GIVEN win rate đã seed tháng 6
- WHEN user bấm Tải đề xuất
- THEN cột Hiệu suất hiển thị `80.0% (12/15)` cho T98 STL

---

### REQ-EP-004: Backtest endpoint alignment

`GET /forum/experts/backtest?days=90` SHOULD đọc từ `expert_win_rates` khi `period=rolling_90d` tồn tại; nếu không, compute live như hiện tại.

**Scenario: Consistency**
- GIVEN `expert_win_rates` period `2026-06` có T98 stl 12/15
- WHEN `GET /forum/experts/performance?period=2026-06`
- AND `GET /forum/recommendations` live_experts T98
- THEN `rate_pct` khớp (80.0)

---

### REQ-EP-005: Không đổi weight JSON tự động

Seed win rate **không** tự ghi `expert_weights.json` (tách biệt hiệu suất hiển thị vs trọng số scoring).

Refresh weights vẫn qua `POST /forum/experts/weights/refresh` (existing).

**Scenario: Tách concerns**
- GIVEN seed win rate tháng 6
- THEN `expert_weights.json` không thay đổi trừ khi gọi `weights/refresh` explicit
