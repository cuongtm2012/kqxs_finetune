# Tasks: Fix Popup Height / Layout

## Phase 1: Fix HTML/body height

- [ ] **T1.1** CSS: `html { max-height: 600px; }` — bỏ `height: 100vh`, `overflow: hidden`
- [ ] **T1.2** CSS: `body { max-height: 600px; }` — bỏ `height: 100vh`
- [ ] **T1.3** Keep: `body { display: flex; flex-direction: column; gap: var(--space-2); }`

## Phase 2: Fix tab-panel scroll

- [ ] **T2.1** CSS: `.tab-panel { flex: 1; min-height: 0; overflow-y: auto; padding-bottom: var(--space-3); }`
- [ ] **T2.2** CSS: `.tab-panel.hidden { display: none; }` (giữ nguyên)
- [ ] **T2.3** CSS: Settings panel `.collapsed` transition giữ nguyên

## Phase 3: Build + verify

- [ ] **T3.1** `npm run build` — thành công
- [ ] **T3.2** Load extension → popup hiển thị đúng height
- [ ] **T3.3** Tab Đề xuất với nhiều data → scroll trong panel
- [ ] **T3.4** Header + tabs + settings luôn visible
- [ ] **T3.5** Settings expand/collapse không làm hỏng layout
