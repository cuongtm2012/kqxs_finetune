# Spec Delta: Forum Ingest API

## ADDED Requirements

### REQ-FI-001: POST /forum/picks

API SHALL accept extension `CollectSession` JSON and persist to Postgres.

**Scenario: Ingest thành công**
- GIVEN valid body với `target_date`, `posts`, `summary`
- WHEN `POST /forum/picks`
- THEN return `{"ok": true, "target_date": "...", "pick_count": N}`
- AND `forum_sessions` upserted
- AND `forum_user_picks` replaced for that date

**Scenario: Dedupe latest pick**
- GIVEN user `T98` post STL `68,86` lúc 20:00 và `12,21` lúc 21:00 cùng ngày D
- WHEN ingest
- THEN chỉ lưu `12,21` cho `(T98, stl)`

---

### REQ-FI-002: GET /forum/picks/{date}

**Scenario: Lấy session**
- GIVEN session tồn tại cho `2026-07-01`
- WHEN `GET /forum/picks/2026-07-01`
- THEN return full payload JSONB

**Scenario: Không có data**
- WHEN `GET /forum/picks/2099-01-01`
- THEN HTTP 404

---

### REQ-FI-003: Reject empty session overwrite

`ingest_collect_session` SHALL refuse body với `posts: {}` khi DB đã có dữ liệu cho `target_date`.

**Điều kiện từ chối (HTTP 400):**
- `posts` rỗng AND (`forum_user_picks` có rows OR session payload cũ có `posts` không rỗng)

**Scenario: Extension sync rỗng sau poll fail**
- GIVEN API đã có 87 posts / 104 picks cho `2026-07-07`
- WHEN `POST /forum/picks` với `posts: {}`
- THEN HTTP 400 `refusing empty session for 2026-07-07`
- AND picks/posts hiện có không bị xóa

**Scenario: Lần ingest đầu rỗng**
- GIVEN chưa có picks và chưa có session posts
- WHEN `POST` với `posts: {}`
- THEN vẫn upsert (metadata-only) — hành vi hiện tại
