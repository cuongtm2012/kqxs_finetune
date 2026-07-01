# Design: Forum Collector Chrome Extension

## Architecture

```
extension/
├── manifest.json
├── openspec/                    # Spec artifacts (this folder)
├── src/
│   ├── background/
│   │   └── service-worker.ts    # Scheduler, alarm, orchestration
│   ├── content/
│   │   ├── forum-parser.ts      # DOM extraction (XenForo)
│   │   └── content-script.ts    # Inject on forumketqua.net/*
│   ├── lib/
│   │   ├── date-window.ts       # Target date + collect window logic
│   │   ├── forum-auth.ts        # Session check + XenForo login
│   │   ├── thread-discovery.ts  # Find daily threads from forum list
│   │   ├── pick-parser.ts       # STL/BTL/de/dàn parsers (port từ crawl_forum_picks.py)
│   │   ├── forum-html-parser.ts # Fetch + parse thread HTML
│   │   ├── collector.ts         # Poll orchestration
│   │   ├── recommendations-api.ts  # GET /forum/recommendations (popup)
│   │   ├── storage.ts           # chrome.storage.local wrapper
│   │   └── api-client.ts        # POST full CollectSession to API
│   ├── popup/
│   │   ├── popup.html
│   │   ├── popup.ts
│   │   └── popup.css
│   └── types/
│       └── forum.ts             # Shared TypeScript interfaces
├── config/
│   ├── forum-auth.example.json  # Template (committed)
│   └── forum-auth.local.json    # Credentials thật (gitignored)
└── package.json                 # esbuild / vite build
```

## Component Diagram

```mermaid
flowchart TB
    subgraph Browser
        SW[Service Worker]
        CS[Content Script]
        POP[Popup UI]
        ST[(chrome.storage.local)]
    end

    subgraph Forum
        F1[Khu mở bát]
        F2[Thảo luận XSMB]
        F3[Chăn nuôi]
    end

    subgraph API
        API[FastAPI :18715]
    end

    SW -->|ensureLoggedIn| CS
    CS -->|XenForo login| Forum
    SW -->|chrome.alarms 5min| CS
    CS -->|fetch DOM| F1
    CS -->|fetch DOM| F2
    CS -->|fetch DOM| F3
    CS -->|parsed posts| SW
    SW --> ST
    POP --> SW
    SW -->|optional POST| API
```

## Key Technical Decisions

### 1. Manifest V3 + Service Worker

- `chrome.alarms` poll mỗi **5 phút** trong cửa sổ collect (configurable).
- Ngoài cửa sổ: alarm tắt hoặc poll 30 phút chỉ check thread mới.
- `host_permissions`: `https://forumketqua.net/*`, `http://localhost:18715/*`, `http://127.0.0.1:18715/*`, `http://localhost:8081/*`, `http://127.0.0.1:8081/*` (API fallback)

### 2. Thread Discovery (thay KNOWN_DAILY_IDS)

Mỗi sub-forum daily có pattern title:

| Forum | Regex title (case-insensitive) |
|-------|-------------------------------|
| mo_bat | `Mở bát\s+.+\s+(\d{1,2})[/.](\d{1,2})[/.](\d{4})` |
| thao_luan | `THẢO LUẬN.*NGÀY\s+(\d{1,2})[/.](\d{1,2})[/.](\d{4})` |

Flow:
1. Fetch forum listing page 1 (`/forums/{slug}/`)
2. Parse `<a class="PreviewTooltip"` hoặc `data-preview-url` trong thread list
3. Match title → extract date → map `target_date → thread_url`
4. Cache trong storage; refresh khi vào `collect_start`

Chăn nuôi: thread dài hạn — lưu danh sách thread "active" (STL K2N, BTL K3N, 40s, 36s, 64s) trong config; poll **last N pages** hoặc posts có timestamp trong cửa sổ.

### 3. Post Extraction (XenForo DOM)

Reuse selectors đã research trong `scripts/crawl_forum_picks.py`:

```html
<li class="message" data-author="USERNAME" id="post-POSTID">
  <a class="username">USERNAME</a>
  <time class="DateTime" data-time="UNIX_MS">...</time>
  <blockquote class="messageText">CONTENT</blockquote>
</li>
```

Dedupe key: `post_id` (numeric từ `id="post-3915912"`).

Incremental: chỉ parse posts có `data-time > last_seen_timestamp` per thread.

### 4. Date Window Logic

```typescript
function getTargetDate(now: Date, tz: string): Date {
  // Nếu now >= 18:30 hôm nay (tz) → target = ngày mai
  // Ngược lại → target = hôm nay
}

function isInCollectWindow(now: Date, target: Date, tz: string): boolean {
  // start = (target - 1 day) @ 18:30
  // end   = target @ 18:00
}

function shouldFinalize(now: Date, target: Date, tz: string): boolean {
  // now >= target @ 18:15
}
```

Chủ nhật: XSMB không quay → skip collect, hiển thị "Nghỉ CN" trong popup.

### 5. Pick Parser

Port regex từ `crawl_forum_picks.py`:
- `extract_stl`, `extract_btl`, `extract_de_info`, `extract_dan_de`, `extract_muc_lo`

Output per post:

```typescript
interface ForumPost {
  post_id: string;
  thread_id: string;
  forum: 'mo_bat' | 'thao_luan' | 'chan_nuoi';
  user: string;
  posted_at: string;      // ISO8601
  raw_content: string;
  picks: {
    stl?: string[];
    btl?: string[];
    de?: { cham: string[]; tong: string[]; dau: string[] };
    dan_de?: string[];
    muc_lo?: Record<number, string[]>;
  };
}
```

### 6. Storage Schema

```typescript
interface CollectSession {
  target_date: string;           // "2026-07-01"
  window_start: string;
  window_end: string;
  finalized_at?: string;
  threads: Record<string, ThreadState>;
  posts: Record<string, ForumPost>;  // keyed by post_id
  summary: ForumDaySummary;        // aggregated, same shape as crawl_forum_picks output
}

interface ThreadState {
  url: string;
  title: string;
  last_post_time: number;
  last_page_fetched: number;
}
```

### 7. API Integration

```
POST /forum/picks
Body: full CollectSession (posts + summary + window metadata)

GET /forum/recommendations?target_date=YYYY-MM-DD
Response: forum-only picks (source: "forum")
```

Extension settings: `api_base_url` (default `http://localhost:18715`), `auto_sync` toggle.

Popup tab **Đề xuất** gọi API trực tiếp qua `recommendations-api.ts` (không qua service worker). Tự fallback port `8081` / `127.0.0.1` nếu primary fail.

> Port `18715` khớp `APP_PORT` env của backend (`app/config.py` default). **Không** dùng `PORT=`.

`api-client.ts` sync full session sau finalize khi `auto_sync=true`.

### 8. Forum Authentication

Tài khoản mặc định (seed từ `config/forum-auth.local.json`):

| Field | Value |
|-------|-------|
| Username | `kinosa89` |
| Password | `hanchechat` |
| Login URL | `https://forumketqua.net/login/` |

**Flow (`forum-auth.ts`):**

```
ensureLoggedIn()
  ├─ hasValidSession()? → return OK
  ├─ load credentials from chrome.storage.local
  ├─ open/focus tab forumketqua.net/login (hoặc dùng fetch + cookie)
  ├─ extract _xfToken từ form
  ├─ POST /login/login { login, password, remember=1, _xfToken }
  └─ verify cookie xf_session → save auth_status
```

Gọi `ensureLoggedIn()` trước mỗi poll cycle và khi nhận redirect `/login/`.

### 9. Security & Privacy

- Password lưu `chrome.storage.local` (Chrome OS keychain encrypt) — **không** commit `forum-auth.local.json`.
- Spec ghi credentials để dev setup; production đổi qua popup Settings.
- Không gửi credentials ra ngoài `forumketqua.net`.
- Không gửi forum data ra ngoài trừ `api_base_url` user cấu hình.

## Build Tooling

- TypeScript + esbuild (nhẹ, không cần framework)
- `npm run build` → `dist/` load unpacked trong Chrome
- ESLint optional

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Session expire giữa poll | Auto re-login `kinosa89`, retry 1 lần |
| Forum đổi HTML/XenForo theme | Parser dùng `data-author` + `messageText` — ổn định hơn regex thuần |
| Thread title format đổi | Nhiều regex fallback; manual override URL trong settings |
| User tắt Chrome | Extension chỉ chạy khi browser mở — document rõ; có thể bổ sung server fallback |
| Rate limit | Poll 5 phút; backoff khi HTTP 429 |
| Chăn nuôi thread nhiều trang | Chỉ fetch trang cuối + posts mới theo timestamp |

## Relation to Existing Code

| Existing | Extension reuse |
|----------|-----------------|
| `scripts/crawl_forum_picks.py` | Port parsers + output schema |
| `app/prediction/models/forum_consensus.py` | Consumer của exported JSON |
| `TARGET_USERS` lists | Configurable trong extension settings |
