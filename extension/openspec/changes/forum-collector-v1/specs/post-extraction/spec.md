# Spec Delta: Post Extraction & Parsing

## ADDED Requirements

### REQ-PE-001: XenForo Post Parsing

Content script SHALL extract từ mỗi `<li class="message">`:

| Field | Source |
|-------|--------|
| `post_id` | `id="post-{N}"` |
| `user` | `data-author` hoặc `a.username` |
| `posted_at` | `time.DateTime[data-time]` (unix ms → ISO) |
| `raw_content` | `blockquote.messageText` (strip HTML) |
| `thread_id` | URL path `/threads/{slug}.{id}/` |

**Scenario: Parse post hợp lệ**
- GIVEN DOM có message block với user `T98` và content chứa `STL: 68, 86`
- WHEN `extractPosts(document)` chạy
- THEN trả về 1 `ForumPost` với `user=T98`, `picks.stl=["68","86"]`

**Scenario: Bỏ qua post quá ngắn**
- GIVEN `raw_content` length < 15 sau strip HTML
- WHEN parse
- THEN post bị skip

---

### REQ-PE-002: Incremental Fetch

Extension SHALL chỉ ingest posts mới:

- Dedupe theo `post_id` globally trong session.
- Per thread: skip posts có `posted_at <= thread.last_post_time` (trừ lần fetch đầu).

**Scenario: Không duplicate**
- GIVEN post `3915912` đã lưu
- WHEN poll lại cùng thread
- THEN post không được thêm lần 2

---

### REQ-PE-003: Pick Extractors

Port logic từ `scripts/crawl_forum_picks.py`:

| Extractor | Patterns | Output |
|-----------|----------|--------|
| `extract_stl` | `STL: dd, dd`, `cặp dd, dd` | `string[]` 2 số |
| `extract_btl` | `BTL: dd` | `string[]` |
| `extract_de_info` | `chạm`, `tổng`, `đề đầu` | `{cham,tong,dau}` |
| `extract_dan_de` | ≥30 số 2 chữ số hợp lệ | `string[]` |
| `extract_muc_lo` | `Mức: N (` blocks | `Record<muc, numbers[]>` |

**Scenario: Parse BTL**
- GIVEN content `BTL: 31 chốt kèo`
- WHEN `extract_btl(content)`
- THEN `["31"]`

**Scenario: Parse dàn đề**
- GIVEN content có 40 số 2 chữ số liên tục
- WHEN `extract_dan_de(content)`
- THEN trả về mảng unique 40 số

---

### REQ-PE-004: Target User Filter

Settings SHALL cho phép danh sách `target_users` (default từ `crawl_forum_picks.py`). Summary aggregation ưu tiên target users nhưng vẫn lưu tất cả posts.

**Default target users:**
```
LangThang1977, Haiphong27, T98, TieuToanPhong, nhcsxh, gimala,
HoangTin333, Lookingfor, dogati, quedau1981, emvatoi213, BaMinhBeo,
Nhu_Y, Kubi247, 113
```

**Scenario: Summary chỉ highlight target users**
- GIVEN 50 users post STL
- AND 3 users trong `target_users`
- WHEN build `summary.stl_frequency`
- THEN frequency tính trên target users (giống crawl script)
- AND `posts` vẫn chứa full data

---

### REQ-PE-005: Pagination

Thread dài (chăn nuôi) SHALL fetch trang cuối trước:

1. Parse `PageNav` → `lastPage`
2. Fetch `/threads/{slug}/page-{lastPage}`
3. Nếu không có post mới trong window → dừng, không fetch thêm trang cũ

Daily threads thường 1 trang đủ cho ngày hiện tại.

**Scenario: Chỉ fetch trang mới**
- GIVEN `last_post_time` = T
- AND page 50 không có post sau T
- WHEN poll
- THEN không fetch page 49, 48, ...
