# Tasks: UI/UX Overhaul — Forum Collector

## Phase 0: Design tokens + reset

- [ ] **U0.1** Add `@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');` at top of `popup.css`
- [ ] **U0.2** Add `:root` design tokens block (REQ-UI-001)
- [ ] **U0.3** Replace `*` reset with `*, *::before, *::after` and update body typography (REQ-UI-002)

## Phase 1: Component restyling

- [ ] **U1.1** Header: h1 font size/weight, .icon-btn, .badge color mapping
- [ ] **U1.2** Tab bar: pill-style, active/inactive states, transitions (REQ-UI-004)
- [ ] **U1.3** Card system: update all `.card` styles (REQ-UI-005)
- [ ] **U1.4** Button system: primary/secondary/danger/small variants (REQ-UI-006)
- [ ] **U1.5** Tab Đề xuất dual panel: side-by-side layout (REQ-UI-007)
- [ ] **U1.6** Pick chips: pill-style (REQ-UI-008)
- [ ] **U1.7** Dan board: grid layout với monospace numbers (REQ-UI-009)
- [ ] **U1.8** Tables: sticky header, hover highlight, row-hit (REQ-UI-010)

## Phase 2: Transitions + animations

- [ ] **U2.1** Tab panel: opacity fade 150ms
- [ ] **U2.2** Settings panel: smooth slide collapse/expand (REQ-UI-011)
- [ ] **U2.3** Pick-who popup: opacity transition 150ms
- [ ] **U2.4** Collapse buttons: chevron rotate animation
- [ ] **U2.5** Loading bar: keep existing gradient animation

## Phase 3: Color token migration

- [ ] **U3.1** Replace ALL color literals with CSS variables
- [ ] **U3.2** Replace ALL border-color/background with corresponding tokens
- [ ] **U3.3** Replace ALL shadow values with shadow variables
- [ ] **U3.4** Verify no remaining hardcoded colors (grep for `#` in popup.css)

## Phase 4: Build + verify

- [ ] **U4.1** `npm run build` — must succeed
- [ ] **U4.2** Check `dist/popup.css` contains design tokens
- [ ] **U4.3** Visual check all 4 tabs render correctly
- [ ] **U4.4** Verify animations: tab switch, settings collapse, popup
