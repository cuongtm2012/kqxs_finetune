# Spec Delta: Ingest & Settlement Pipeline

## ADDED Requirements

### REQ-ISP-001: Pipeline Contract

Hệ thống SHALL tuân thủ chuỗi nghiệp vụ cố định:

```
CollectSession → POST /forum/picks → forum_user_picks → run_daily_settlement → expert_pick_results → GET /forum/score
```

Tab Kết quả SHALL chỉ đọc từ `expert_pick_results` / `forum_user_picks`, không crawl forum.

**Scenario: Luồng đầy đủ**
- GIVEN extension sync session `2026-07-04` với post có pick hợp lệ
- WHEN `POST /forum/picks` thành công
- AND `POST /forum/score/run?target_date=2026-07-04`
- THEN `GET /forum/score?target_date=2026-07-04` trả row cho user đó

**Scenario: Thiếu sync**
- GIVEN post chỉ có trong forum, chưa sync
- WHEN `GET /forum/score`
- THEN user không xuất hiện (đúng thiết kế — không phải bug chấm)

---

### REQ-ISP-002: Ingest Response Coverage

`POST /forum/picks` response SHALL include `coverage` summary từ `body.threads`.

**Scenario: Response đầy đủ**
- GIVEN body có `threads.thao_luan.backfill_complete`, `lowest_page_fetched`, `last_page_fetched`
- WHEN ingest
- THEN response:
```json
{
  "ok": true,
  "target_date": "2026-07-04",
  "pick_count": 75,
  "post_count": 129,
  "coverage": {
    "threads": [
      {
        "key": "thao_luan",
        "backfill_complete": false,
        "lowest_page_fetched": 8,
        "last_page_fetched": 17
      }
    ]
  }
}
```

---

### REQ-ISP-003: Replace Picks Per Date

Ingest SHALL `DELETE` + `INSERT` `forum_user_picks` cho `target_date` (snapshot semantics — giữ hành vi hiện tại).

**Scenario: Re-sync bổ sung post**
- GIVEN lần 1: 35 post thảo luận
- AND lần 2 sync: 120 post (backfill xong)
- WHEN ingest lần 2
- THEN `pick_count` tăng phản ánh snapshot mới
- AND không duplicate rows cũ

---

### REQ-ISP-004: Dedupe & Cutoff (xác nhận)

Scoring SHALL dùng cùng quy tắc ingest + cutoff:

| Rule | Giá trị |
|------|---------|
| Collect window | `[18:30 D−1, 18:00 D)` ICT |
| Score cutoff | `posted_at < 18:00 D` ICT |
| Dedupe | Latest post per `(username, pick_type)` |

**Scenario: Duong145 03/07 22:09**
- GIVEN post trong collect window cho target `2026-07-04`
- AND `posted_at` = `2026-07-03 22:09` ICT
- WHEN score
- THEN được tính (trước 18:00 ngày 04/7)

**Scenario: Post sau 18:00 ngày D**
- GIVEN `posted_at` = `2026-07-04 18:17` ICT
- WHEN score
- THEN loại khỏi eligible picks

---

### REQ-ISP-005: Settlement Idempotent

`POST /forum/score/run` SHALL idempotent: import draw (nếu cần) + ghi đè `expert_pick_results` cho ngày đó.

**Scenario: Chấm lại sau sync bổ sung**
- GIVEN đã chấm 39/75 hits
- AND sync thêm pick → 90 picks
- WHEN `run_daily_settlement`
- THEN `summary.total` cập nhật
- AND hits tính lại toàn bộ

---

### REQ-ISP-006: Auto Settlement Hook

Sau finalize + sync (18:31+), scheduler hoặc extension MAY trigger `run_daily_settlement` nếu draw đã có.

**Scenario: Cron 18:31**
- GIVEN `forum_user_picks` đã có cho hôm nay
- AND mketqua có KQXS
- WHEN scheduler chạy
- THEN score persisted, tab Kết quả load được ngay

---

### REQ-ISP-007: Score API Coverage Field

`GET /forum/score` SHALL trả `coverage` khi có `forum_sessions` cho `target_date`.

**Scenario: Cảnh báo backfill chưa xong**
- GIVEN `threads.thao_luan.backfill_complete` = false
- WHEN `GET /forum/score`
- THEN `coverage.threads[].backfill_complete` = false
- AND `ok` vẫn true nếu đã có results

---

## MODIFIED Requirements

### REQ-FI-001: POST /forum/picks (mở rộng)

Bổ sung `post_count` và `coverage` trong response (REQ-ISP-002).

### REQ-ST-001: Tab Kết quả (mở rộng)

Document rõ: nguồn pick = Thu thập; hiển thị `coverage` hint (xem `score-tab-completeness`).

---

### REQ-ISP-005: Empty session sync guard (v1.5.5+)

| Layer | Rule |
|-------|------|
| Extension `pushSessionToApi` | Skip khi `posts` rỗng |
| Extension `loadRecommendations` | Sync sau poll chỉ khi `posts > 0` |
| Extension `collector` | `syncSessionToApi` chỉ khi `postCount > 0` |
| API `ingest_collect_session` | HTTP 400 nếu `posts` rỗng và DB đã có picks/session posts (REQ-FI-003) |

**Scenario: Chấm kết quả không bị wipe**
- GIVEN server backfill 90 posts
- WHEN extension poll fail và cố sync `{}`
- THEN API 400 OR extension skip — data server giữ nguyên
