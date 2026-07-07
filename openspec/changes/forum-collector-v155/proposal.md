# Proposal: Forum Collector v1.5.5–1.5.6

## Why

Poll extension thất bại (0 posts) đã sync session rỗng lên API và wipe picks. Crawl HTML từ service worker thiếu cookie. Parser `danExtractChunk` crash trên post mở bát.

## What

| Area | Change |
|------|--------|
| Extension v1.5.6 | Tab fetch via `executeScript` MAIN world; skip empty API sync |
| Ingest | `REQ-FI-003` reject empty overwrite |
| Auth | Public crawl khi login fail; `pageHasReadableForumContent` |
| Parser | `let m` in `danExtractChunk` |
| Scoring doc | `REQ-EW-008` win rate ≠ effective rank |

## Spec deltas

- `forum-intelligence-v1/specs/forum-ingest/spec.md` — REQ-FI-003
- `forum-collect-to-score-v1/specs/ingest-settlement-pipeline/spec.md` — REQ-ISP-005
- `forum-collect-to-score-v1/specs/pick-parser-completeness/spec.md` — REQ-PP-004
- `forum-recommendation-scoring-v3/specs/effective-weight/spec.md` — REQ-EW-008
- `extension/.../forum-auth/spec.md` — REQ-AUTH-006/007
- `extension/.../recommendations-tab/spec.md` — REQ-RT-006
