# Forum Collector — Chrome Extension

Thu thập pick XSMB từ [forumketqua.net](https://forumketqua.net/forums/xo-so-mien-bac/) theo cửa sổ 18:30 → 18:00 (giờ VN).

## Cài đặt (dev)

```bash
cd extension
npm install
npm run build
```

Chrome → `chrome://extensions` → **Developer mode** → **Load unpacked** → chọn folder `extension/dist/`.

## Sử dụng

1. Mở popup extension — kiểm tra **Đã đăng nhập** (auto login `kinosa89`).
2. Trong cửa sổ collect (18:30 hôm qua → 18:00 hôm nay), extension poll mỗi 5 phút.
3. Lúc **18:15** finalize session; bấm **Export JSON** hoặc bật **Auto sync API**.
4. **Poll ngay** để test thủ công.

## Cấu trúc

```
extension/
├── dist/              # Build output — load vào Chrome
├── src/
│   ├── background/    # Service worker + scheduler
│   ├── content/       # Content script (forum DOM)
│   ├── lib/           # Parser, auth, collector
│   └── popup/         # UI
├── config/            # forum-auth.local.json (gitignored)
└── openspec/          # SPEC artifacts
```

## API sync

POST `http://localhost:18715/forum/picks` — full `CollectSession`.

Tab **Đề xuất** → `GET /forum/recommendations` (forum-only, không engine).

Chạy API: `APP_PORT=18715 python run.py`

## Đăng nhập forum

| Username | `kinosa89` |
| Password | Lưu trong popup / `config/forum-auth.local.json` |

## OpenSpec

Chi tiết: [`openspec/changes/forum-collector-v1/`](openspec/changes/forum-collector-v1/)
