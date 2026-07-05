# Spec Delta: Recommendations Scoring v3

## MODIFIED Requirements

### REQ-REC-001: GET /forum/recommendations (scoring)

Thay `expert_weight()` bằng `scoring_w(user, pick_type)` trong mọi aggregation:

| Function | Thay đổi |
|----------|----------|
| `_aggregate_loto_scores` | `score(n) += scoring_w(user, pt)` |
| `_aggregate_loto_consensus` | `weight_sum += scoring_w`; tie-break 1-vote dùng `scoring_w` |
| `_best_btl` | max `scoring_w` per BTL number |
| `_de_top4` | `de_scores[n] += scoring_w` (×1.5 cho `btd`) |
| `_de_cham_leaders` | sort `-effective_weight` |
| `_collect_dan_board` | sort `-effective_weight`; field `weight` giữ manual |
| `_forum_confidence` | `avg(scoring_w)` thay `avg(weight)` |

`scoring_w` implementation:

```python
def _scoring_w(user: str, pt: str, mode: str, period: str) -> float:
    if mode == "weight":
        return expert_weight(user, pt)
    return expert_effective_weight(user, pt, mode=mode, period_label=period)
```

**Scenario: nhcsxh không dominate BTL (blend)**
- GIVEN `nhcsxh` `w_manual=1.0`, BTL perf `1/2` rolling_90d
- AND cao thủ khác BTL `2/2` với `w_manual=0.3`, `effective ≈ 0.25`
- WHEN `scoring_mode=blend`, `_best_btl(picks)`
- THEN result MAY NOT be số chỉ từ `nhcsxh` nếu consensus/other cao thủ có `scoring_w` cao hơn

**Scenario: weight mode unchanged**
- WHEN `scoring_mode=weight`
- THEN `btl_lo` và `forum_loto_top10` order khớp v2

---

### REQ-REC-002: Picks output unchanged shape

`picks.btl_lo`, `picks.bao_lo_9`, `picks.de_top_4`, `consensus.picks.*` — cùng JSON keys.

Chỉ **giá trị** thay đổi theo scoring mode (expected).

---

### REQ-REC-003: Confidence recalibration

```python
confidence = min(1.0, 0.15 + expert_count * 0.06 + avg_scoring_w * 0.25)
```

`avg_scoring_w` = mean `scoring_w` của `live_experts` (no-dan panel).

**Scenario: low-confidence day**
- GIVEN nhiều cao thủ `effective_weight < 0.2` (blend, thiếu mẫu)
- THEN `confidence` thấp hơn ngày nhiều cao thủ `effective > 0.5`

---

### REQ-REC-004: de_top_4 weight key consistency

Trong `_de_top4`, khi đọc `dan_board` row:

```python
w = row.get("effective_weight") or _scoring_w(row["user"], resolved_pt, ...)
```

Không dùng `row["weight"]` (manual) cho scoring khi mode ≠ weight.

---

### REQ-REC-005: Consensus de_top_4

`_de_top4_consensus` — **không đổi** (vote count only).

Panel đồng thuận đề vẫn pure consensus; panel trọng số đề dùng effective.

---

## ADDED Requirements

### REQ-REC-006: Audit script

`scripts/audit_reco_scoring.py`:

```bash
PYTHONPATH=. .venv/bin/python scripts/audit_reco_scoring.py \
  --target-date 2026-07-05 \
  --users nhcsxh,himle79,Qtv1,T98 \
  --modes weight,blend,measured
```

Output table: user, pick_type, w_manual, effective, perf, btl_lo contributor.

Exit 1 nếu `blend` effective > `w_manual` khi `total=0` (gate failure).

---

### REQ-REC-007: Integration test

`tests/test_reco_scoring_blend.py`:

- Mock picks + perf → assert `nhcsxh` effective < 0.5 khi no/small sample
- Assert `scoring_mode=weight` score == legacy
- Assert response includes `scoring_mode`, `effective_weight`
