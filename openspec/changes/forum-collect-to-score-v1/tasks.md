# Tasks: Forum Collect → Score Pipeline v1

## Phase 1 — Collector backfill (P0)

- [ ] **T1.1** `collector.ts`: refresh `last_page` mỗi cycle (REQ-CB-001)
- [ ] **T1.2** `collector.ts`: sửa điều kiện `backfill_complete` — page 1 hoặc minTs < window start (REQ-CB-002)
- [ ] **T1.3** `collector.ts`: finalize gate — defer khi `backfill_complete=false`, grace 30 phút (REQ-CB-004)
- [ ] **T1.4** `storage.ts` / `forum.ts`: type `coverage_warning` trên session nếu finalize grace
- [ ] **T1.5** `popup.ts`: hiển thị backfill progress per thread (REQ-CB-005, REQ-SC-004)
- [ ] **T1.6** Test: mock HTML 17 pages → assert post page 3, 7 ingested

## Phase 2 — Parser (P0)

- [ ] **T2.1** `pick-parser.ts`: STL dot `27.72` → `27, 72` (REQ-PP-001)
- [ ] **T2.2** `pick-parser.ts`: `4 số`, `1 số`, `To bộ` (REQ-PP-002)
- [ ] **T2.3** `pick-parser.ts` + `forum-html-parser.ts`: strip XenForo quote trước parse (REQ-PP-003)
- [ ] **T2.4** `forum_crawl_service.py`: parity với T2.1–T2.3 (REQ-PP-004)
- [ ] **T2.5** `tests/test_pick_parser_dot_stl.py`, `tests/test_pick_parser_de_4so.py`, `tests/test_pick_parser_quote_strip.py`
- [ ] **T2.6** Regression `tests/test_pick_parser_multiday.py`

## Phase 3 — API pipeline (P1)

- [ ] **T3.1** `forum_ingest_service.py`: response `post_count`, `coverage` (REQ-ISP-002)
- [ ] **T3.2** `expert_score_service.py`: `get_scored_day` merge `coverage` từ session (REQ-ISP-007)
- [ ] **T3.3** `forum.py`: document response schema (optional OpenAPI comment)
- [ ] **T3.4** Verify `run_daily_settlement` idempotent sau re-sync (REQ-ISP-005)

## Phase 4 — Score tab UI (P1)

- [ ] **T4.1** `score-api.ts`: type `coverage` trên `DrawScoreResponse`
- [ ] **T4.2** `popup.ts` `renderScore`: hint post_count + coverage warning (REQ-SC-001, REQ-SC-002)
- [ ] **T4.3** `popup.css`: style badge cảnh báo vàng

## Phase 5 — Audit & verification (P1)

- [ ] **T5.1** `scripts/audit_collect_score.py`:
  - Input: `--date`, `--thread-slug`
  - Crawl forum picks in window vs `forum_user_picks` vs score hits
  - Output: missing winners với post_id, page
- [ ] **T5.2** Chạy audit `2026-07-04` — baseline trước fix (document expected gaps)
- [ ] **T5.3** Sau implement: force poll → sync → score/run → audit exit 0

## Phase 6 — Docs (P2)

- [ ] **T6.1** Cập nhật `extension/openspec/.../score-tab/spec.md` cross-ref change này
- [ ] **T6.2** README hoặc comment popup: "Kết quả = KQXS + pick đã Thu thập"

## Acceptance checklist

| # | Kiểm tra | Pass |
|---|----------|------|
| A1 | Duong145 STL 55,87 hit sau full pipeline | ☐ |
| A2 | Tornado6789 BTL 87 hit | ☐ |
| A3 | 36QueToi STL 27,72 hit (lô 27) | ☐ |
| A4 | congtush150i quote không tạo pick | ☐ |
| A5 | Tab Thu thập hiện 17/17 ✓ | ☐ |
| A6 | Tab Kết quả không cảnh báo khi đủ | ☐ |
| A7 | `pytest` parser + backfill tests pass | ☐ |

## Ưu tiên triển khai

```
P0: T1.* + T2.*  →  fix thiếu winner (root cause)
P1: T3.* + T4.* + T5.*  →  minh bạch + audit
P2: T6.*  →  docs
```

## Effort ước lượng

| Phase | Effort |
|-------|--------|
| 1 Collector | 0.5–1 ngày |
| 2 Parser | 0.5 ngày |
| 3 API | 0.25 ngày |
| 4 UI | 0.25 ngày |
| 5 Audit | 0.5 ngày |
| **Tổng** | **~2–2.5 ngày** |
