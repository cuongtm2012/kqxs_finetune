# Spec Delta: Engine Tab (Popup)

## ADDED Requirements

### REQ-ET-001: Tab Engine

Popup SHALL có tab **Engine** fetch bundle từ API qua `engine-api.ts`.

Khi mở tab hoặc bấm **Tải engine**:
- `GET /stats/candidates?target_date=…`
- `GET /stats/de-candidates?target_date=…`
- `GET /stats/intersection?target_date=…`
- `GET /predictions/next?target_date=…` (best-effort)
- `GET /analytics/summary` (DB draw range)

Port fallback giống tab Đề xuất (`18715` → `8081`).

**Scenario: DB stale**
- GIVEN `analytics.newest` cách hôm nay > 1 ngày
- THEN hiển thị cảnh báo vàng gợi ý import KQXS

---

### REQ-ET-002: Engine UI sections

| Section | Nguồn |
|---------|-------|
| Meta (ngày, as-of, DB draws, API) | bundle metadata |
| Stats Engine — Lô | `stats_loto.candidates` |
| Stats Engine — Đề | `stats_de.candidates` |
| Giao CF × RBK | `intersection` (cf/rbk/final) |
| Prediction (legacy) | `predictions.predictions` |

Tab Engine SHALL NOT trộn forum picks — tách biệt tab Đề xuất.
