# Proposal: Forum Recommendation Scoring v3 — Effective Weight & Measured Scoring

## WHY

Sau win-rate v2, **Hiệu suất hiển thị đã chính xác hơn**, nhưng **đề xuất số vẫn scoring theo W thủ công** (`expert_weights.json`) — hai pipeline tách biệt gây hiểu nhầm và đề xuất kém chính xác.

**Vấn đề đã verify (2026-07-04):**

| Hiện tượng | Nguyên nhân |
|------------|-------------|
| `nhcsxh` #1 bảng cao thủ, chiếm `btl_lo` | W=1.0 từ JSON; không có BTL đo được tháng 6 |
| `himle79` dàn W=0.94 nhưng đo được ~53.8% | W = track record cũ; scoring không dùng measured rate |
| `Qtv1` từng hiện BTL 100% (3/3) | Backtest 90d gắn nhãn period tháng 6 (đã fix lookup) |
| Cao thủ `1/1 (100%)*` ngang `7/13 (53.8%)` khi sort Hiệu suất | Không shrinkage mẫu nhỏ trong scoring |
| Period cố định `2026-06` khi đã tháng 7 | Active user thiếu mẫu period nhưng W vẫn full |

**Mục tiêu v3:** Đề xuất số (lô, BTL, đề top 4, confidence) dùng **effective weight** = blend W thủ công + hiệu suất đo được, có gate mẫu nhỏ — vẫn giữ W gốc để audit.

## WHAT

| # | Thành phần | Mô tả |
|---|------------|-------|
| 1 | **`expert_effective_weight()`** | Wilson lower bound × W_manual × sample ramp; gate `total < MIN` |
| 2 | **Scoring mode** | `weight` \| `measured` \| `blend` (default `blend`) trên API + extension |
| 3 | **Period rolling** | `DEFAULT_PERIOD_LABEL = rolling_90d`; calendar month qua query/env |
| 4 | **Recommendation scoring** | `_aggregate_loto_scores`, `_de_top4`, `_best_btl`, consensus tie-break dùng effective_w |
| 5 | **API metadata** | `scoring_mode`, `scoring_period`, `effective_weight` trên `live_experts` / `dan_board` |
| 6 | **Extension UI** | Legend scoring mode; toggle W / Hiệu suất / Effective (sort) |
| 7 | **Tests + audit** | Unit Wilson/gate; integration nhcsxh/himle79; `audit_reco_scoring.py` |

**Ngoài scope v3:**

- Time decay theo `posted_at` (v4)
- Tự động ghi `expert_weights.json` từ measured (vẫn explicit refresh)
- Win rate theo từng số trong dàn
- Engine hybrid trong API

## SUCCESS

1. `scoring_mode=blend`: `nhcsxh` BTL **không** đứng đầu `forum_loto_top10` chỉ vì W=1.0 khi `total < 3` trong period.
2. `himle79` chốt STL: effective weight ≤ `0.3` (gate + category); chốt `dan_40s`: effective ≈ `0.94 × wilson(7/13)` < W thuần nếu rate thấp hơn JSON.
3. `GET /forum/recommendations` trả `scoring_mode`, `scoring_period=rolling_90d`; `live_experts[].effective_weight` khác `weight` khi có measured data.
4. `scoring_mode=weight` giữ hành vi cũ (backward compat) cho A/B so sánh.
5. Extension: legend *"Đề xuất dùng effective weight (blend)"*; sort thêm cột Effective.
6. `pytest tests/test_effective_weight.py tests/test_reco_scoring*.py` pass; audit script exit 0 cho top 10 user.

## DEPENDENCIES

- `forum-expert-winrate-v2` — shared `expert_pick_eval`, `expert_performance`, purge period
- `expert_win_rates` seeded `rolling_90d`
- `forum-intelligence-v1` — recommendations API baseline

## RELATED

- `openspec/changes/forum-expert-winrate-v2/` — W vs Hiệu suất, lookup fixes
- `openspec/changes/forum-intelligence-v1/specs/recommendations/` — ranking rules v1
- `extension/openspec/changes/forum-collector-v1/specs/recommendations-tab/`
