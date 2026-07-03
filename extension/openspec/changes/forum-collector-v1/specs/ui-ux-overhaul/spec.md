# Spec Delta: Popup UI/UX Overhaul

## MODIFIED requirements

### REQ-RT-005: Settings panel (thay đổi layout)

Settings panel SHALL slide down với smooth transition khi toggle.

---

## ADDED requirements

### REQ-UI-001: Design System Tokens

Popup CSS SHALL use CSS custom properties (design tokens) at `:root`:

```css
:root {
  --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
  --scale-xs: 10px;
  --scale-sm: 11px;
  --scale-base: 13px;
  --scale-lg: 15px;
  --scale-xl: 18px;
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --radius-sm: 4px;
  --radius-md: 6px;
  --radius-lg: 8px;
  --radius-xl: 12px;
  --radius-full: 9999px;
  --color-bg: #f8fafc;
  --color-surface: #ffffff;
  --color-border: #e2e8f0;
  --color-border-light: #f1f5f9;
  --color-text: #0f172a;
  --color-text-secondary: #64748b;
  --color-text-muted: #94a3b8;
  --color-accent: #2563eb;
  --color-accent-hover: #1d4ed8;
  --color-accent-light: #eff6ff;
  --color-success: #059669;
  --color-success-bg: #ecfdf5;
  --color-warning: #d97706;
  --color-warning-bg: #fffbeb;
  --color-danger: #dc2626;
  --color-danger-bg: #fef2f2;
  --color-rose: #f43f5e;
  --color-rose-bg: #fff1f2;
  --shadow-card: 0 1px 3px 0 rgba(0,0,0,0.06), 0 1px 2px -1px rgba(0,0,0,0.06);
  --shadow-popup: 0 10px 25px -3px rgba(0,0,0,0.1);
  --transition-fast: 150ms ease;
}
```

### REQ-UI-002: Global reset & typography

```css
*, *::before, *::after { box-sizing: border-box; }
body {
  margin: 0;
  padding: var(--space-4);
  width: 680px;
  max-width: 720px;
  font-family: var(--font-sans);
  font-size: var(--scale-base);
  line-height: 1.5;
  color: var(--color-text);
  background: var(--color-bg);
  -webkit-font-smoothing: antialiased;
}
```

### REQ-UI-003: Header refinement

- h1: `font-size: var(--scale-xl)`, `font-weight: 700`, `letter-spacing: -0.02em`
- Badge status: pill với color mapping (green=collecting, blue=finalized, gray=idle, yellow=waiting, red=error/sunday)
- Icon button (gear): 32x32, border, hover → accent. When settings open → active state blue fill

### REQ-UI-004: Tab bar

- Tab buttons: pill-style (`border-radius: var(--radius-full)`)
- Active tab: `background: var(--color-accent)`, `color: var(--color-surface)`, `font-weight: 600`
- Inactive tab: `background: transparent`, `color: var(--color-text-secondary)`, `border: 1px solid var(--color-border)`
- Tab transition: `background var(--transition-fast)`
- Tab panel switch: `opacity` transition 150ms (fade in/out)
- Khoảng cách tabs: `gap: var(--space-1)`

### REQ-UI-005: Card system

- Uniform `.card`: `background: var(--color-surface)`, `border: 1px solid var(--color-border)`, `border-radius: var(--radius-lg)`, `padding: var(--space-3)`, `box-shadow: var(--shadow-card)`
- Card margin-bottom: `var(--space-3)`
- Card hover (optional): `box-shadow` tăng nhẹ

### REQ-UI-006: Button system

- Primary button: `background: var(--color-accent)`, `color: var(--color-surface)`, `font-weight: 600`
- Secondary button: `background: var(--color-text-secondary)`, `color: var(--color-surface)`
- Danger button: `background: var(--color-danger)`
- Hover: `filter: brightness(1.08)` cho tất cả
- Focus-visible: `outline: 2px solid var(--color-accent)`, `outline-offset: 2px`
- Disabled: `opacity: 0.7`, `cursor: not-allowed`
- Small variant: `padding: var(--space-1) var(--space-2)`, `font-size: var(--scale-xs)`

### REQ-UI-007: Tab Đề xuất — dual panel side-by-side

Khi popup width >= 680px, dual panel (trọng số + đồng thuận) SHALL render side-by-side:

```css
.reco-dual-panels {
  display: flex;
  gap: var(--space-3);
}
.reco-dual-panels > .card {
  flex: 1;
  min-width: 0;
}
```

### REQ-UI-008: Pick chips

- Inline pill: `display: inline-flex`, `padding: 1px 6px`, `border-radius: var(--radius-sm)`
- Default: `background: var(--color-accent-light)`, `border: 1px solid var(--color-border)`, `cursor: pointer`
- Hover: `border-color: var(--color-accent)`, `color: var(--color-accent)`
- Active/focus: focus-visible outline
- Chips trong "bao lô" hiển thị vote count suffix: `n×2` cho vote >= 2

### REQ-UI-009: Dan board grid

- Numbers display in `.dan-nums-grid`: `display: flex`, `flex-wrap: wrap`, `gap: var(--space-1)`
- Each number: `font-family: var(--font-mono)`, `font-size: var(--scale-sm)`, `padding: 1px 4px`, `border-radius: var(--radius-sm)`
- Overlap number (≥2 users): `background: var(--color-rose-bg)`, `border: 1px solid var(--color-rose)`, `color: #9f1239`, `font-weight: 700`

### REQ-UI-010: Tables

- `.reco-table`: `width: 100%`, `border-collapse: collapse`, `font-size: var(--scale-sm)`
- th: `color: var(--color-text-muted)`, `font-weight: 600`, `text-transform: uppercase`, `letter-spacing: 0.04em`, `padding: var(--space-1) var(--space-1)`
- td: `padding: var(--space-1)`, `border-bottom: 1px solid var(--color-border-light)`
- tr hover: `background: var(--color-accent-light)`
- tr.row-hit td: `background: var(--color-success-bg)`
- Sticky header: `position: sticky`, `top: 0`, `background: var(--color-surface)`, `z-index: 1`

### REQ-UI-011: Smooth transitions

- `.settings-panel`: `max-height` transition + `opacity` transition 200ms ease when collapsed/expanded
- `.tab-panel`: `opacity` transition 150ms ease, start at 0 when hidden
- `.pick-who-popup`: `opacity` transition 150ms ease
- Collapse buttons: smooth `rotate` on chevron

### REQ-UI-012: Google Fonts

SHALL load Inter (400, 500, 600, 700) via `@import` in CSS đầu file:
```css
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
```

### REQ-UI-013: Color token migration

All hardcoded colors in existing CSS SHALL be replaced with the corresponding CSS variable. No color literals remain except in the `:root` block.

### REQ-UI-014: Class restructuring

Existing CSS classes SHALL be renamed only where needed for clarity:
- `.reco-loading` → `.loading-bar` (keep `.reco-loading` as alias)
- `.reco-loading-bar-fill` → `.loading-bar-fill`
- No other class renames (minimize HTML changes)

### REQ-UI-015: Build verification

After CSS changes: `npm run build` SHALL succeed.
Resulting `dist/popup.css` SHALL contain all design tokens.
