# Proposal: Forum Expert Win Rate v2 — Accuracy & Alignment

## WHY

Sau khi audit (2026-07-04), tab **Đề xuất** vẫn gây hiểu nhầm:

1. **W (trọng số)** và **Hiệu suất (win rate)** là hai nguồn khác nhau nhưng UI xếp hạng theo W → user tưởng top 1 = win rate cao nhất.
2. `himle79` W=0.94 từ `expert_weights.json` (track record thủ công 17/18 dàn 40s) nhưng **0 pick tháng 6** trong DB → `expert_win_rates` không có row; backtest 90d chỉ **1/2 dan_40s (50%)**.
3. `expert_performance(user, "dan_de")` không khớp pick_type lưu DB (`dan_40s`, `dan_36s`, `dan_64s`) → cột Hiệu suất dàn thường `—`.
4. `expert_weight(user, "stl")` fallback `default` → cao thủ dàn (himle79 94%) nhận W cao khi chốt STL — **sai loại pick**.
5. `run_backtest()` không `canonical_username` / dedupe per-day → lệch so với `expert_winrate_service`.
6. Backfill tháng 6 v1 chỉ ~5 ngày cuối tháng — thiếu cao thủ dàn lớn (himle79, Xuannd, Binhrau1).

**Ví dụ thực tế (đã verify DB):**

| User | W (JSON) | DB performance tháng 6 | Backtest 90d |
|------|----------|-------------------------|--------------|
| himle79 | 0.94 `dan_de` | không có row | dan_40s 1/2 (50%) |
| nhcsxh | 1.0 `stl` | btl 3/3 (100%) | khớp |
| Xuannd | 0.91 `dan_de` | không có row | dan_40s 0/1 (0%) |

Cần SPEC v2 để **tách rõ W vs win rate**, **sửa lookup**, **đồng bộ backtest**, **backfill đủ mẫu**, và **UI minh bạch**.

## WHAT

| # | Thành phần | Mô tả |
|---|------------|-------|
| 1 | **Backfill tháng 6 mở rộng** | Crawl đủ topic chăn nuôi + daily; ưu tiên cao thủ dàn trong `xsmb_cao_thu_trackrecord.md` |
| 2 | **Seed + `rolling_90d`** | Re-seed `2026-06`; thêm period `rolling_90d` tự refresh sau ingest/settlement |
| 3 | **Performance lookup chain** | `dan_de` → `dan_40s` / `dan_36s` / `dan_64s` → `default` → backtest |
| 4 | **Weight theo pick_type** | Không dùng `default` dàn cho `stl`/`btl`/`muc_lo`; unknown pick_type → `0.3` |
| 5 | **Backtest alignment** | `run_backtest()` dùng cùng dedupe + `canonical_username` như winrate service |
| 6 | **Extension UI** | Ghi chú W vs Hiệu suất; tùy chọn sort bảng theo `rate_pct`; tooltip period |
| 7 | **Audit script** | `scripts/audit_expert_winrate.py` — so sánh JSON weights vs DB vs backtest cho N user |

**Ngoài scope v2:**

- Tự động ghi `expert_weights.json` từ win rate (vẫn qua `POST /forum/experts/weights/refresh` explicit)
- Win rate theo từng số trong dàn
- Real-time re-seed sau mỗi poll extension (scheduler hook — v3)

## SUCCESS

1. `himle79` có row `expert_win_rates` period `2026-06`, pick_type `dan_40s`, `total ≥ 15`, `rate_pct` trong ±2% so với track record thủ công (17/18 ≈ 94.4%) sau backfill + audit.
2. `GET /forum/recommendations` → `dan_board[].performance` ≠ `null` cho cao thủ có `total ≥ 3` tháng 6.
3. `himle79` chốt STL: `weight ≤ 0.3` (hoặc key `stl` riêng nếu có) — **không** inherit 0.94 từ dàn.
4. `run_backtest(90)` và `compute_period_stats(rolling_90d)` cho cùng user/pick_type khớp `hits/total`.
5. Extension: bảng cao thủ có legend *"W = trọng số scoring · Hiệu suất = hit/total kỳ 2026-06"*; sort mặc định vẫn W, có toggle sort theo Hiệu suất.
6. `scripts/audit_expert_winrate.py --users himle79,Xuannd` exit 0 khi JSON/DB/backtest documented deltas nằm trong ngưỡng.

## DEPENDENCIES

- `forum-expert-winrate-v1` (migration 005, services, API) — **đã có**
- `scripts/backfill_forum_picks_month.py`, `scripts/seed_expert_win_rates.py`
- `xsmb_cao_thu_trackrecord.md` — ground truth thủ công để spot-check
- `draw_repo.get_mb_ketqua` — KQXS tháng 6 đã có

## RELATED

- `openspec/changes/forum-expert-winrate-v1/` — baseline v1
- `openspec/changes/forum-intelligence-v1/specs/expert-scoring/` — weight & live experts
- `extension/openspec/changes/forum-collector-v1/specs/recommendations-tab/` — UI tab Đề xuất
