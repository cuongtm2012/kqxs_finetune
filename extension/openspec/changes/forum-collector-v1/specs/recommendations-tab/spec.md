# Spec Delta: Recommendations Tab (Popup)

## ADDED Requirements

### REQ-RT-001: Tab Đề xuất

Popup SHALL có 2 tab: **Thu thập** | **Đề xuất**.

Tab Đề xuất SHALL fetch `GET {api_base_url}/forum/recommendations?target_date={runtime.target_date}` khi mở tab hoặc bấm **Tải đề xuất**.

Fetch SHALL chạy trong popup (`recommendations-api.ts`), không bắt buộc qua service worker.

**Scenario: Load thành công**
- GIVEN API healthy và có forum picks
- WHEN user mở tab Đề xuất
- THEN hiển thị BTL lô, bao lô 9, xiên 2, đề top 4, danh sách cao thủ, bảng top lô cao thủ

**Scenario: API offline**
- THEN hiển thị lỗi rõ: không kết nối / thiếu `/forum` / hướng dẫn `APP_PORT=18715 python run.py`

**Scenario: Fallback port**
- GIVEN `api_base_url` là `:18715` unreachable nhưng `:8081` có `/forum`
- WHEN fetch
- THEN dùng `:8081` AND lưu lại `api_base_url` mới vào settings

---

### REQ-RT-002: Forum-only UI

Tab Đề xuất SHALL NOT hiển thị engine score, hybrid score, hay độ tin cậy engine.

| Element | Nguồn API |
|---------|-----------|
| Cao thủ chốt | `expert_count` |
| BTL / Bao lô / Xiên / Đề | `picks.*` |
| Chạm đề | `de_cham_leaders[]` |
| Danh sách cao thủ | `live_experts[]` |
| Top lô cao thủ | `forum_loto_top10[]` — cột Trọng số + Cao thủ |

**Scenario: Chưa có cao thủ**
- THEN `live_experts` empty message: "Chưa có cao thủ chốt (poll + sync API)"

---

### REQ-RT-003: Settings panel

Auth + API settings SHALL nằm trong panel ⚙️ (collapsible), không che tab Đề xuất.

Khi đã login forum: ẩn form username/password, hiện hint "Đã đăng nhập".
