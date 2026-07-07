# Spec Delta: Forum Authentication

## ADDED Requirements

### REQ-AUTH-001: Default Forum Account

Extension SHALL dùng tài khoản forum mặc định để tự đăng nhập khi chưa có session hợp lệ:

| Field | Value |
|-------|-------|
| `username` | `kinosa89` |
| `password` | `hanchechat` |
| `login_url` | `https://forumketqua.net/login/` |
| `remember` | `true` (Duy trì đăng nhập) |

Credentials lưu trong `chrome.storage.local` key `forum_auth`, seed từ `extension/config/forum-auth.local.json` lúc cài extension. User có thể đổi qua popup Settings.

> **Bảo mật:** Không commit `forum-auth.local.json` lên git. Chỉ `forum-auth.example.json` (placeholder) được track.

---

### REQ-AUTH-002: Session Detection

Trước mỗi poll cycle, extension SHALL kiểm tra đã login chưa.

**Dấu hiệu đã login (bất kỳ):**
- Cookie `xf_user` hoặc `xf_session` tồn tại cho `forumketqua.net`
- DOM không còn form `#LoginForm` / link "Đăng nhập" ở header
- Fetch `/account/` trả về 200 (không redirect về `/login/`)

**Scenario: Đã login — skip login**
- GIVEN browser có session hợp lệ forumketqua.net
- WHEN `ensureLoggedIn()` chạy
- THEN không gọi login AND tiếp tục poll

**Scenario: Chưa login — auto login**
- GIVEN không có session
- AND `forum_auth` có username/password
- WHEN `ensureLoggedIn()` chạy
- THEN submit login form AND session được thiết lập

---

### REQ-AUTH-003: XenForo Login Flow

Login SHALL thực hiện qua XenForo form chuẩn:

1. `GET https://forumketqua.net/login/` → lấy `_xfToken` (CSRF) từ hidden input
2. `POST https://forumketqua.net/login/login` với body:
   ```
   login=kinosa89
   password=hanchechat
   remember=1
   _xfToken={token}
   ```
3. Verify response: redirect về trang chủ hoặc `/forums/`, cookie session set

**Implementation:** Content script trên tab forum hoặc `chrome.scripting.executeScript` mở tab ẩn `/login/`, fill form, submit.

**Scenario: Login thành công**
- GIVEN credentials đúng
- WHEN POST login
- THEN `auth_status = "logged_in"` AND `last_login_at` được lưu

**Scenario: Login thất bại**
- GIVEN credentials sai hoặc forum trả lỗi
- WHEN POST login
- THEN `auth_status = "error"` AND popup hiển thị "Đăng nhập forum thất bại"
- AND poll **vẫn tiếp tục** crawl nội dung công khai (thread không cần login)
- AND `last_poll_status` MAY = `login_retry_public`

---

### REQ-AUTH-006: Tab-context HTML fetch (v1.5.5+)

Service worker `fetch()` không chia sẻ cookie forum đầy đủ. Extension SHALL ưu tiên fetch HTML qua tab `forumketqua.net`:

1. `ensureForumTab()` — mở/reuse tab forum (inactive)
2. `chrome.scripting.executeScript({ world: "MAIN", func: fetch(url, {credentials:"include"}) })` — primary
3. Fallback: content script message `FETCH_FORUM_HTML`
4. Fallback cuối: service worker `forumFetch()`

`fetchForumHtml()` chấp nhận HTML khi `pageHasReadableForumContent(html)` (có `post-*`, thread links, hoặc pageNav).

**Scenario: Poll force**
- WHEN `runPollCycle({ force: true })`
- THEN `clearForumHtmlCache()` AND `ensureForumTab()` trước crawl

---

### REQ-AUTH-007: Login page false positive

`isLoginPage()` SHALL NOT trả `true` khi:
- `isLoggedInHtml(html)`, hoặc
- `pageHasReadableForumContent(html)` (thread công khai có posts dù footer có form login ẩn)

CSRF token: `extractXfToken` SHALL match `[_\-]` trong `csrf=` embed (Google login link).

---

### REQ-AUTH-004: Session Refresh

Nếu poll nhận HTTP 403 hoặc redirect `/login/` giữa chừng:

1. Clear auth status
2. Gọi lại `ensureLoggedIn()`
3. Retry fetch tối đa 1 lần

**Scenario: Session hết hạn giữa poll**
- GIVEN đang collect, session expire
- WHEN fetch thread trả redirect login
- THEN auto re-login AND retry fetch

---

### REQ-AUTH-005: Popup Auth UI

Popup SHALL hiển thị:

| Element | Mô tả |
|---------|-------|
| Auth badge | `Logged in` / `Not logged in` / `Login failed` |
| Username | `kinosa89` (readonly hoặc editable) |
| Password | masked input, có nút show/hide |
| Button | "Đăng nhập lại" / "Test login" |

**Scenario: Manual re-login**
- GIVEN user click "Đăng nhập lại"
- WHEN credentials hợp lệ
- THEN session refresh AND badge = `Logged in`
