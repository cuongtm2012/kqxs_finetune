# Spec Delta: Export & Sync

## ADDED Requirements

### REQ-EX-001: Summary Schema

`summary` output SHALL tương thích `scripts/crawl_forum_picks.py`:

```json
{
  "date": "2026-07-01",
  "weekday": "Thứ Tư",
  "target_date": "2026-07-01",
  "collected_at": "2026-07-01T18:14:00+07:00",
  "forums": {
    "mo_bat": { "thread_url": "...", "post_count": 12 },
    "thao_luan": { "thread_url": "...", "post_count": 847 },
    "chan_nuoi": { "threads": [...], "post_count": 34 }
  },
  "stl_k2n_users": {},
  "btl_k3n_users": {},
  "daily_users": {},
  "muc_lo": {},
  "dan_de": [],
  "de_cham_leaders": [],
  "stl_frequency": {},
  "btl_frequency": {},
  "all_posts": []
}
```

`all_posts` là superset mới (optional cho backend) — không phá consumer cũ nếu bỏ qua field này.

---

### REQ-EX-002: Local Storage

Mỗi `target_date` SHALL có 1 `CollectSession` trong `chrome.storage.local`:

- Key: `session:{target_date}`
- Retention: giữ 30 ngày, auto-prune session cũ

**Scenario: Persist qua restart browser**
- GIVEN session đang collect
- WHEN user đóng và mở lại Chrome
- THEN session được restore AND poll tiếp tục

---

### REQ-EX-003: JSON Export

Popup SHALL có nút **Export JSON** → download file:

```
rbk-forum-{target_date}.json
```

Chứa full `CollectSession` (posts + summary).

**Scenario: Manual export**
- GIVEN user click Export
- WHEN session tồn tại
- THEN file JSON được tải về qua `chrome.downloads`

---

### REQ-EX-004: API Sync (Optional)

Nếu `settings.auto_sync = true` AND `settings.api_base_url` reachable:

```
POST {api_base_url}/forum/picks
Content-Type: application/json
Body: full CollectSession object (posts, summary, target_date, window_*)
```

`api-client.ts` thử fallback bases: primary URL → `localhost:18715` → `localhost:8081` → `127.0.0.1:*`.

**Scenario: Auto sync sau finalize**
- GIVEN `auto_sync=true`, API healthy
- WHEN finalize lúc 18:15
- THEN POST summary AND lưu `last_sync_status` trong storage

**Scenario: API offline**
- GIVEN POST failed
- THEN retry 3 lần exponential backoff AND popup hiển thị warning

---

### REQ-EX-005: Popup Status UI

Popup SHALL hiển thị:

| Element | Mô tả |
|---------|-------|
| Target date | Ngày quay đang collect |
| Window | `collect_start → collect_end` |
| Status badge | `Idle` / `Collecting` / `Finalized` / `Sunday skip` |
| Counters | Posts mới / tổng posts / threads found |
| Thread links | Click mở tab forum |
| Settings | timezone, poll interval, target users, API URL |
| Actions | Export JSON, Force poll now, Clear session |
| Tab Đề xuất | Forum picks từ API — xem `specs/recommendations-tab/spec.md` |

**Scenario: Live counter**
- GIVEN 5 posts mới từ poll vừa rồi
- WHEN user mở popup
- THEN counter tăng 5 so với lần trước
