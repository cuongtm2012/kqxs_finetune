# Tasks: Fix recommendation target date + Popup height

## Phase 1: Fix recommendation target date

- [ ] **T1.1** Check `loadRecommendations()` in `src/popup/popup.ts`:
  - `getTargetDate(now, settings.timezone)` at line 1276 → verify value after 18:30 ICT
  - After cutoff, force poll if `runtime.target_date !== target` 
  - Force sync session to API after poll
  - Refetch recommendations
  
- [ ] **T1.2** Add rolled-over detection:
  ```ts
  const runtime = await getRuntimeStatus();
  const rolledOver = Boolean(runtime.target_date && runtime.target_date !== target);
  if (rolledOver) {
    // Force poll + sync
    await pollNowWithTimeout();
    await syncSessionOptional(session, true);
    data = await fetchRecommendationsAndSyncUrl(target, settings);
  }
  ```

- [ ] **T1.3** Test: sau 18:30, mở popup → tab Đề xuất hiển thị target_date = D+1 (03/07 nếu hôm nay 02/07 sau 18:30)
- [ ] **T1.4** Test: nếu API offline, hiển thị error message rõ ràng

## Phase 2: Popup height full viewport

- [ ] **T2.1** Update `popup.css`:
  - `html, body { height: 100vh; max-height: 100vh; overflow: hidden; }`
  - `.tab-panel` không hidden: `height: calc(100vh - 140px); overflow-y: auto;`
  - Header, tab bar, settings panel: `flex-shrink: 0` (không bị co)
  - Body: `display: flex; flex-direction: column; gap: var(--space-2);`

- [ ] **T2.2** Settings panel expanded: cần tính toán lại height? Hoặc để panel scroll tự handle.

- [ ] **T2.3** Verify: scroll trong panel content, không scroll cả popup

- [ ] **T2.4** Build: `npm run build` ✅

## Phase 3: Build + verify

- [ ] **T3.1** `npm run build` — thành công
- [ ] **T3.2** Load extension → popup chiều cao full viewport
- [ ] **T3.3** Tab Đề xuất target_date = 03/07
- [ ] **T3.4** Scroll trong panel không ảnh hưởng header/tabs
