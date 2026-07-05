# Spec Delta: Expert Weight by Pick Type

## MODIFIED Requirements

### REQ-ES-001: Expert Weights (v2)

`expert_weight(username, pick_type)` SHALL resolve weight **theo đúng category pick**, không leak trọng số dàn sang lô.

**Pick type categories:**

| Category | Keys |
|----------|------|
| LOTO | `stl`, `btl`, `muc_lo` |
| DAN | `dan_de`, `dan_40s`, `dan_36s`, `dan_64s` |
| DE_META | `de_cham`, `de_dau`, `de_tong`, `btd`, `btd_dau`, `btd_de`, `std_de` |

**Lookup order:**

1. `weights[user][pick_type]` nếu tồn tại
2. **DAN request** (`dan_40s` etc.): `weights[user]["dan_de"]` hoặc `weights[user]["default"]` nếu user chỉ có keys dàn
3. **LOTO request**: `weights[user]["stl"]` / `btl` / `muc_lo` hoặc `default` **chỉ khi** user có ít nhất một key LOTO hoặc `default` không phải profile dàn-only
4. **DE_META request**: key tương ứng hoặc `default`
5. Unknown user hoặc không match → `0.3`

**Dàn-only profile:** user có `dan_de` và/hoặc `default` nhưng **không** có key nào trong `LOTO` ∪ `DE_META`.

**Scenario: himle79 STL (v2 fix)**
- GIVEN `{"default": 0.94, "dan_de": 0.94}` — không có `stl`
- WHEN `weight("himle79", "stl")`
- THEN `0.3` (NOT 0.94)

**Scenario: himle79 dan_40s**
- WHEN `weight("himle79", "dan_40s")`
- THEN `0.94` (via `dan_de` family)

**Scenario: T98 STL**
- GIVEN `{"stl": 0.95, "default": 0.95}`
- WHEN `weight("T98", "stl")`
- THEN `0.95` (unchanged)

**Scenario: nhcsxh cross-category**
- GIVEN `{"default": 1.0, "stl": 1.0}`
- WHEN `weight("nhcsxh", "btl")`
- THEN `1.0` (via default — user có LOTO keys)

---

## ADDED Requirements

### REQ-EW-001: Weight ≠ win rate (documentation)

`expert_weights.json` SHALL remain **tách biệt** khỏi `expert_win_rates`.

- Seed / refresh win rate **không** tự ghi weights file (giữ REQ-EP-005 v1)
- README và extension legend MUST state: **W = scoring weight**, **Hiệu suất = measured hit rate**

**Scenario: User audit**
- GIVEN himle79 W=0.94 và performance 50% (2 ngày tháng 7)
- THEN UI hiển thị cả hai số, không gộp

---

### REQ-EW-002: Optional explicit stl key

Khi refresh weights (`POST /forum/experts/weights/refresh`), `suggest_weights()` SHOULD chỉ blend vào key pick_type có `total ≥ 3` trong backtest — không ghi `stl` cho user chỉ có dàn.

**Scenario: suggest_weights himle79**
- GIVEN backtest chỉ có `dan_40s`
- THEN suggested JSON không thêm key `stl`
