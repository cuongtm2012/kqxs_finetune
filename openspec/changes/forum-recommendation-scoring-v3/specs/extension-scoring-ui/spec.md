# Spec: Extension Scoring UI v3

## MODIFIED Requirements

### REQ-ESU-001: Scoring mode toggle

Extension tab **Đề xuất** SHALL persist `reco_scoring_mode` in `chrome.storage.local`:

| Value | Label |
|-------|-------|
| `blend` | Blend (mặc định) |
| `weight` | W thủ công (cũ) |
| `measured` | Chỉ đo được |

API call:

```
GET /forum/recommendations?target_date=...&scoring_mode={reco_scoring_mode}
```

**Scenario: user chọn "W thủ công"**
- THEN request `scoring_mode=weight`
- AND loto scores khớp behavior trước v3

---

### REQ-ESU-002: Legend update

Thay legend v2:

```
W = trọng số thủ công · Hiệu suất = hit/total ({period})
Đề xuất số dùng: {scoring_mode_label} · kỳ {scoring_period_label}
```

`scoring_mode_label` map:
- `blend` → "Effective (blend)"
- `weight` → "W thủ công"
- `measured` → "Hiệu suất đo được"

---

### REQ-ESU-003: Expert table columns

Bảng cao thủ (`live_experts`, `dan_board`):

| Cột | Field | Sortable |
|-----|-------|----------|
| W | `weight` | yes (default off when blend) |
| Hiệu suất | `performance` | yes |
| Eff. | `effective_weight` | yes (default on when blend) |

Sort key `reco_expert_sort` mở rộng: `weight` | `performance` | `effective`.

Khi `scoring_mode=weight`: hide Eff. column hoặc show = W.

**Scenario: blend default sort**
- GIVEN `reco_scoring_mode=blend`
- THEN default sort `effective` desc

---

### REQ-ESU-004: Low sample indicator

Giữ `*` suffix trên Hiệu suất khi `low_sample`.

Thêm tooltip Eff.: *"Wilson + mẫu {total}/{MIN_SAMPLE}"* khi `performance.total < 5`.

---

### REQ-ESU-005: Types

`recommendations-api.ts`:

```typescript
export type ScoringMode = "weight" | "measured" | "blend";

export interface ExpertRow {
  weight: number;
  effective_weight?: number;
  performance?: ExpertPerformance | null;
}

export interface RecommendationsResponse {
  scoring_mode: ScoringMode;
  scoring_period: string;
  scoring_period_label: string;
  // ...existing
}
```

---

### REQ-ESU-006: No extension scoring logic duplication

Extension SHALL NOT compute Wilson/blend locally — chỉ hiển thị API fields.

---

## OUT OF SCOPE

- Chart/compare modes side-by-side
- Push notification khi scoring_mode đổi kết quả btl_lo
