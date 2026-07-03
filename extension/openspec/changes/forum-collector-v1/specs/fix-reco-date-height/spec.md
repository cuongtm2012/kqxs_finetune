# Spec Delta: Fix recommendation target date + Popup height

## MODIFIED requirements

### REQ-RT-001: Tab Đề xuất — target date logic (MODIFIED)

Sau 18:30 ICT:
- `getTargetDate()` trả về D+1 (ngày quay tiếp theo)
- Recommendations API SHALL gọi với target_date = D+1
- **Nếu API trả về target_date cũ (D-1 hoặc D cũ)**, popup SHALL:
  - Bấm **Tải đề xuất** để force refetch
  - Hiển thị cảnh báo màu vàng nếu API date khác với expected date

**Bug hiện tại**: `loadRecommendations()` dùng `getTargetDate()` chính xác, nhưng:
1. Session cũ chưa rolled over → API trả data cũ
2. Popup tab **Đề xuất** không tự động force poll khi target_date thay đổi sau cutoff

**Fix**:
- `loadRecommendations()` sau khi get target, check nếu `runtime.target_date !== target` (rolled over), force poll session mới
- Gọi `pollNowWithTimeout()` + sync session + refetch

---

### REQ-UI-016: Popup height — full viewport (ADDED)

Popup SHALL take maximum available height:
- No fixed `max-height` on body
- `.tab-panel` active panel SHALL `overflow-y: auto` với `max-height: calc(100vh - header - tabs - spacing)`
- Scrollbar only on active content panel, not the entire popup
- Header + tabs + settings SHALL remain sticky/visible when scrolling panel content

**Implementation approach**:

```css
html, body {
  height: 100vh;
  max-height: 100vh;
  overflow: hidden;
}

#panel-collect, #panel-reco, #panel-engine, #panel-score {
  height: calc(100vh - 140px); /* header (~40px) + tabs (~36px) + settings (~40px) + padding (~24px) */
  overflow-y: auto;
}
```

The 140px offset compensates for fixed-height elements (header, tab bar, settings panel, bottom padding). Each panel scrolls independently.

**Scenarios**:
- Nhiều cao thủ (20+ rows in expert table) → panel scrolls, header stays
- Dan board với nhiều dàn → scroll trong panel
- Settings expanded → subtract additional height from panel
