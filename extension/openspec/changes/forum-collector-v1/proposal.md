# Proposal: Chrome Extension — Forumketqua XSMB Collector

## WHY

Hệ thống hiện crawl forum qua server (`scripts/crawl_forum_picks.py`, `forum_consensus.py`) nhưng gặp hạn chế:

- **Không có session đăng nhập** — một số nội dung forum bị giới hạn khi chưa login.
- **Thread ID thủ công** — `KNOWN_DAILY_IDS` phải cập nhật tay mỗi ngày; thread tháng mới (40s/36s/64s) cũng đổi URL.
- **Không theo dõi real-time** — cao thủ chốt số trong cửa sổ 18:30 → 18:00; server cron một lần/ngày sẽ bỏ lỡ pick muộn.
- **Rate limit / IP block** — crawl từ server dễ bị chặn khi poll nhiều.

Chrome extension tự đăng nhập forum (tài khoản `kinosa89`), discover thread theo ngày, poll trong cửa sổ collect, parse pick (STL/BTL/đề/dàn) và export JSON hoặc POST về API.

## WHAT

Extension **Forum Collector** thu thập dữ liệu từ 3 sub-forum XSMB trên [forumketqua.net](https://forumketqua.net/forums/xo-so-mien-bac/):

| Sub-forum | URL | Loại thread |
|-----------|-----|-------------|
| Khu mở bát | `/forums/khu-mo-bat.13/` | 1 thread/ngày — "Mở bát Thứ X dd/mm/yyyy" |
| Thảo luận, dự đoán XSMB | `/forums/du-doan-xsmb/` | 1 thread/ngày — "THẢO LUẬN, DỰ ĐOÁN XSMB ... NGÀY dd/m/yyyy" |
| Chăn nuôi XSMB | `/forums/chan-nuoi-xsmb.15/` | Nhiều thread dài hạn (STL K2N, BTL K3N, dàn 40s/36s/64s) + post chốt theo ngày |

### Cửa sổ thời gian (múi giờ mặc định `Asia/Ho_Chi_Minh`)

> User mô tả "GMT" nhưng giờ quay XSMB thực tế là **18:15 giờ Việt Nam**. Spec dùng ICT làm default; có thể override trong settings.

| Mốc | Thời điểm | Ý nghĩa |
|-----|-----------|---------|
| `collect_start` | 18:30 ngày D−1 | Bài post mới gán cho **ngày quay D** |
| `collect_end` | 18:00 ngày D | Hết cửa sổ chốt số |
| `draw_time` | 18:15 ngày D | Bắt đầu quay — finalize snapshot, ngừng poll |

Ví dụ: muốn collect cho **01/07/2026** → poll từ **30/06 18:30** đến **01/07 18:00**, snapshot lúc **01/07 18:15**.

### Phạm vi v1

**Trong scope:**
- Manifest V3 extension (background service worker + content script + popup)
- **Tự động đăng nhập forum** — tài khoản mặc định `kinosa89` / `hanchechat`, session refresh khi hết hạn
- Auto-discover daily threads từ forum listing (title regex ngày)
- Incremental poll 3 sub-forum trong cửa sổ collect
- Parse posts: user, timestamp, STL, BTL, chạm/tổng/đầu đề, dàn đề, mức lô
- Lưu local (chrome.storage) + export JSON + POST full `CollectSession` tới API
- Popup UI: tab **Thu thập** | **Đề xuất** | **Engine** | **Kết quả**

**Ngoài scope v1:**
- Collect sub-forum "Soi cầu XSMB"
- Hybrid engine scoring trong extension (backend API forum-only; hybrid chỉ trong daily report CLI)
- Mobile / Firefox

## SUCCESS CRITERIA

1. Extension tự login forum (`kinosa89`) nếu chưa có session → poll đúng 3 khu.
2. Trước 18:15 ngày quay, mọi post chốt mới trong cửa sổ được ghi nhận (dedupe theo `post_id`).
3. Export JSON tương thích schema mà `scripts/crawl_forum_picks.py` đang produce.
4. Không cần cập nhật `KNOWN_DAILY_IDS` thủ công.
