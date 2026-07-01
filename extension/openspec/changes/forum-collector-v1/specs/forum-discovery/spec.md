# Spec Delta: Forum Discovery

## ADDED Requirements

### REQ-FD-001: Sub-forum Registry

Extension SHALL theo dõi đúng 3 sub-forum:

| Key | Name | Listing URL |
|-----|------|-------------|
| `mo_bat` | Khu mở bát | `https://forumketqua.net/forums/khu-mo-bat.13/` |
| `thao_luan` | Thảo luận, dự đoán XSMB | `https://forumketqua.net/forums/du-doan-xsmb/` |
| `chan_nuoi` | Chăn nuôi XSMB | `https://forumketqua.net/forums/chan-nuoi-xsmb.15/` |

---

### REQ-FD-002: Daily Thread Auto-Discovery

Với `mo_bat` và `thao_luan`, extension SHALL tìm thread có title chứa ngày `target_date` từ trang listing (page 1, fallback page 2).

**Title patterns:**

```
mo_bat:    /Mở bát\s+.+\s+{d}[/.]{m}[/.]{yyyy}/i
thao_luan: /THẢO LUẬN.*NGÀY\s+{d}[/.]{m}[/.]{yyyy}/i
```

Cho phép biến thể: `01/7/2026`, `01/07/2026`, `1/7/2026`.

**Scenario: Discover thread thảo luận**
- GIVEN `target_date` = `2026-07-01` (Thứ Tư)
- WHEN fetch `/forums/du-doan-xsmb/`
- THEN tìm được thread title chứa `01/7/2026` hoặc `01/07/2026`
- AND lưu `thread_url` vào session

**Scenario: Thread chưa tạo**
- GIVEN sau 18:30 nhưng mod chưa mở thread
- WHEN discovery không match
- THEN retry mỗi poll cycle AND popup hiển thị "Chờ thread ngày D"

---

### REQ-FD-003: Chăn Nuôi Long-running Threads

`chan_nuoi` có thread theo tháng/khung (STL K2N, BTL K3N, dàn 40s/36s/64s). Extension SHALL:

1. Giữ danh sách `pinned_threads` trong settings (seed từ defaults, user có thể sửa).
2. Poll các thread này — chỉ lấy posts trong collection window.
3. Auto-detect thread tháng mới: nếu title chứa `THÁNG {m}/{yyyy}` và tháng = tháng của `target_date`, ưu tiên thread mới nhất.

**7 topic ghim** (listing [chăn nuôi](https://forumketqua.net/forums/chan-nuoi-xsmb.15/)) — extension SHALL cố lấy đủ:

| Key | Topic |
|-----|-------|
| `btl_k5n` | TOPIC CHĂN NUÔI XSMB BTL K5N THÁNG M/YYYY |
| `stl_k2n` | NUÔI SONG THỦ LÔ KHUNG 2 NGÀY - THÁNG M/YYYY |
| `btl_k3n` | TOPIC CHĂN NUÔI XSMB BTL K3N THÁNG M/YYYY |
| `dan_64s` | DÀN ĐẶC BIỆT XSMB 64S THÁNG M/YYYY |
| `stl_k3n` | NUÔI SONG THỦ LÔ KHUNG 3 NGÀY - THÁNG M/YYYY |
| `dan_36s` | CHĂN DÀN ĐẶC BIỆT XSMB 36S KHUNG 5 THÁNG M/YYYY |
| `dan_40s` | CHĂN DÀN ĐẶC BIỆT XSMB 40s KHUNG 4 THÁNG M/YYYY |

Logic:
1. Scan listing page 1 — match từng key bằng regex (`CHAN_NUOI_PINNED_TOPICS`).
2. Ưu tiên title chứa `THÁNG {m}/{yyyy}` của `target_date`.
3. Bỏ qua topic **Đã khóa** nếu đã có bản tháng mới cùng loại.
4. Poll mỗi thread — posts trong collection window → picks → `dan_board` / STL / BTL trên tab Đề xuất.

**Default pinned patterns** (legacy settings, discovery dùng `CHAN_NUOI_PINNED_TOPICS`):
- `BTL K5N`, `SONG THU LO KHUNG 2 NGAY`, `BTL K3N`, `64S`, `SONG THU LO KHUNG 3 NGAY`, `36S KHUNG`, `40S KHUNG`

**Scenario: Lấy STL từ thread K2N**
- GIVEN thread STL K2N tháng 7 active
- AND user `T98` post STL `68, 86` lúc 20:00 trong cửa sổ
- WHEN parse thread
- THEN post được gán `forum=chan_nuoi` AND picks.stl = `["68","86"]`

---

### REQ-FD-004: Thread Cache Invalidation

Khi `target_date` đổi (qua 18:30), extension SHALL reset thread cache và chạy discovery lại.

**Scenario: Đổi ngày target**
- GIVEN session đang collect cho `2026-06-30`
- WHEN clock chuyển sang `2026-06-30 18:31`
- THEN `target_date` mới = `2026-07-01`
- AND discovery chạy cho ngày mới
- AND session cũ được finalize (nếu chưa) rồi tạo session mới
