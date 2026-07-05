# Spec Delta: Extension UI — W vs Hiệu suất

## MODIFIED Requirements

### REQ-RT-003: Cao thủ đang chốt table (v2)

Bảng **Cao thủ đang chốt** (`live_experts`, max 20 rows) SHALL:

| Cột | Ý nghĩa | Sort default |
|-----|---------|--------------|
| Cao thủ | username | — |
| Khu / Topic / Loại / Số | unchanged | — |
| **Hiệu suất** | `performance.rate_pct` (hits/total, period từ API) | toggle |
| **W** | scoring weight từ JSON | **desc (default)** |

**Scenario: himle79**
- GIVEN W=0.94, performance=94.4% (17/18) sau backfill v2
- THEN hiển thị `94.4% (17/18)` và `0.94` — hai cột riêng

**Scenario: Low sample**
- GIVEN performance `low_sample: true`
- THEN `50.0% (1/2)*`

---

### REQ-RT-004: Top lô cao thủ (v2)

Bảng **Top lô cao thủ** sort default vẫn **W desc**.

Sub-line dưới username (`expert-loto-perf`) hiển thị Hiệu suất pick_type lô (`stl`/`btl`) — không dùng perf dàn.

**Scenario: himle79 chốt STL**
- GIVEN weight 0.3 (v2 fix), performance null hoặc stl-specific
- THEN không xếp top 1 chỉ vì W dàn 0.94

---

## ADDED Requirements

### REQ-EUI-001: Legend

Tab **Đề xuất**, phía trên bảng cao thủ, SHALL hiển thị:

```
W = trọng số scoring · Hiệu suất = tỷ lệ trúng (kỳ {performance_period_label})
```

Lấy `performance_period` / `performance_period_label` từ API response.

**Scenario: Tháng 6**
- THEN legend contains `kỳ Tháng 6/2026`

---

### REQ-EUI-002: Sort toggle

Header bảng cao thủ có control (button hoặc click header):

- **Theo W** (default) — hành vi scoring hiện tại
- **Theo hiệu suất** — `rate_pct` desc, null cuối; tie-break `total` desc

State lưu `chrome.storage.local` key `reco_expert_sort`: `"weight"` | `"performance"`.

**Scenario: User audit win rate**
- WHEN chọn "Theo hiệu suất"
- THEN nhcsxh 100% có thể đứng trước user W cao nhưng perf thấp

---

### REQ-EUI-003: Dan board performance

Card dàn (`dan_board` / `renderDanBoard`) SHALL hiển thị perf khi có:

```
40s · 40 số · w=0.94 · perf 94.4% (17/18)
```

**Scenario: Trước backfill**
- perf `—` khi null

---

### REQ-EUI-004: Gợi ý loại trừ disclaimer

Section **Gợi ý loại trừ (theo hiệu suất)** SHALL note:

> Chỉ lọc khi ≥3 mẫu trong kỳ. W và hiệu suất là hai chỉ số khác nhau.

(Align với logic `total >= 3` đã có trong `popup.ts`.)

---

### REQ-EUI-005: Không đổi panel đề xuất scoring

Panel **Theo cao thủ (trọng số)** và **Theo đồng thuận** — thuật toán `_de_top4` / consensus **không đổi** trong v2.

Chỉ UI transparency + weight isolation fix ảnh hưởng gián tiếp khi himle79 STL không còn W=0.94.
