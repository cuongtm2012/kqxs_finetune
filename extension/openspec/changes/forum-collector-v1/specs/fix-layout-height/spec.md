# Spec Delta: Fix Popup Height / Layout Breakage

## Root cause analysis

### Issue 1: `100vh` không hoạt động trong Chrome extension popup

Chrome extension popup có `max-height` mặc định (~600px). `height: 100vh` trong CSS không đúng vì popup không phải full viewport — nó là floating panel.

**Fix**: Bỏ `height: 100vh` / `max-height: 100vh` trên `html, body`. Dùng max-height mặc định của Chrome (CSS `max-height` không set = Chrome tự quản lý). Chỉ cần `.tab-panel` scroll nội bộ.

### Issue 2: Tab panel hidden vẫn giữ overflow

`.tab-panel.hidden` dùng `display: none` — đúng. Nhưng khi visible, tab-panel dùng `flex: 1` + `overflow-y: auto` và body dùng `flex-direction: column`. Vấn đề là body cần `max-height` cố định để flex children biết giới hạn.

**Fix**: 
- Bỏ `height: 100vh` / `overflow: hidden` trên `html, body`  
- Body vẫn `display: flex; flex-direction: column;`  
- HTML `max-height: 600px` (Chrome extension default)  
- Tab panel: `flex: 1; min-height: 0; overflow-y: auto;`

### Issue 3: Card margin-bottom bị ăn ở cuối scroll

`.card { margin-bottom: var(--space-3); }` → card cuối cùng margin-bottom bị cắt khi tab-panel có `overflow-y: auto`.

**Fix**: `.tab-panel` có `padding-bottom: var(--space-3)` thay vì dựa vào margin-bottom của card cuối.

---

## MODIFIED requirements

### REQ-UI-016: Popup height (MODIFIED)

**REMOVED**: `html, body { height: 100vh; overflow: hidden; }`

**REPLACED WITH**:
```css
html {
  max-height: 600px; /* Chrome extension popup default */
}
body {
  display: flex;
  flex-direction: column;
  max-height: 600px;
}
```

`.tab-panel` khi không hidden:
```css
.tab-panel {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding-bottom: var(--space-3);
}
```

Settings panel: `flex-shrink: 0` giữ nguyên.

Header + .tabs: `flex-shrink: 0` giữ nguyên.

---

## ADDED requirements

### REQ-UI-017: Popup min-width và padding

Giữ nguyên `width: 680px; max-width: 720px` trên body.
Giữ nguyên `padding: var(--space-4)`.
