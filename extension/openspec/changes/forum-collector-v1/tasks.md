# Tasks: Forum Collector Chrome Extension v1

## Phase 0 — Scaffold
- [x] **T0.1** `extension/package.json` (TypeScript, esbuild, `@types/chrome`)
- [x] **T0.2** `manifest.json` MV3 + host permissions (forum + API ports)
- [x] **T0.3** Build script `npm run build` → `dist/`
- [x] **T0.4** `src/types/forum.ts`

## Phase 1 — Forum Auth
- [x] **T1.0** `src/lib/forum-auth.ts` — XenForo login, CSRF từ `csrf=` trong HTML
- [x] **T1.0b** Seed credentials từ `config/forum-auth.local.json`
- [x] **T1.0c** Popup auth UI (settings panel ⚙️)
- [x] **T1.0d** Login qua content script + reload tab forum

## Phase 2 — Date Window
- [x] **T2.1** `src/lib/date-window.ts`
- [ ] **T2.2** Unit test date-window
- [x] **T2.3** Sunday skip logic

## Phase 3 — Thread Discovery
- [x] **T3.1** `src/lib/thread-discovery.ts`
- [x] **T3.2** Title regex mo_bat, thao_luan
- [x] **T3.3** Pinned threads chăn nuôi
- [x] **T3.4** Cache per target_date

## Phase 4 — Post Extraction
- [x] **T4.1** `src/lib/forum-html-parser.ts` + content script
- [x] **T4.2** `src/lib/pick-parser.ts`
- [x] **T4.3** Dedupe + incremental
- [x] **T4.4** Pagination last page first
- [x] **T4.5** Message passing service worker ↔ content

## Phase 5 — Background Scheduler
- [x] **T5.1** `service-worker.ts` — alarms 5min / idle
- [x] **T5.2** `collector.ts` orchestration
- [x] **T5.3** Finalize 18:15 + `force: true` poll manual
- [x] **T5.4** `storage.ts` + prune 30 days
- [x] **T5.5** `summary.ts` aggregator

## Phase 6 — Popup UI
- [x] **T6.1** `popup.html` + `popup.css` — tabs Thu thập | Đề xuất
- [x] **T6.2** `popup.ts` — bind storage, settings
- [x] **T6.3** Export JSON
- [x] **T6.4** Poll ngay, Clear session

## Phase 7 — API Integration
- [x] **T7.1** `api-client.ts` — POST full CollectSession + port fallback
- [x] **T7.2** Settings `api_base_url`, `auto_sync`
- [x] **T7.3** Backend `POST /forum/picks` (forum-intelligence-v1)

## Phase 8 — Đề xuất Tab
- [x] **T8.1** `recommendations-api.ts` — GET recommendations + fallback
- [x] **T8.2** Popup render forum-only (không engine/hybrid)
- [x] **T8.3** Extension v1.0.7 — chạm đề trên tab Đề xuất

## Phase 9 — QA & Docs
- [ ] **T9.1** So sánh JSON với `crawl_forum_picks.py` cùng ngày
- [ ] **T9.2** Cập nhật `extension/README.md` (APP_PORT, tab Đề xuất)

## Current version

`manifest.json` → **1.0.6**
