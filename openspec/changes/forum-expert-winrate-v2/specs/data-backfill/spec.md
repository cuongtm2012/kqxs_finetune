# Spec Delta: Data Backfill & Seed (v2)

## MODIFIED Requirements

### REQ-JB-003: Thread sources tháng 6 (v2 — full crawl)

Backfill tháng 6 SHALL crawl **toàn bộ pages** (pagination) của topic chăn nuôi, không chỉ trang đầu:

| Key | Thread | Pick types expected |
|-----|--------|-------------------|
| dan_40s | `chan-dan-dac-biet-xsmb-40s-khung-4-thang-6-2026.101212` | `dan_40s` |
| dan_36s | `chan-dan-dac-biet-xsmb-36s-khung-5-thang-6-2026.101211` | `dan_36s` |
| dan_64s | `dan-dac-biet-xsmb-64s-thang-6-2026.101209` | `dan_64s` |
| stl_k2n | `nuoi-song-thu-lo-khung-2-ngay-thang-6-2026.101198` | `stl` |
| btl_k3n | `topic-chan-nuoi-xsmb-btl-k3n-thang-6-2026.101208` | `btl` |

**Scenario: himle79 trong topic 40s**
- WHEN backfill full thread dan_40s
- THEN `forum_user_picks` có ≥15 rows `(himle79, dan_40s)` spread across June draw days

**Scenario: Pagination**
- GIVEN thread có >50 posts
- WHEN crawl
- THEN parser đọc hết pages đến khi post date < `period_start`

---

### REQ-JB-006: Seed win rate sau backfill (v2 acceptance)

Sau backfill v2, seed SHALL produce rows cho **top dàn experts** (minimum set):

`himle79`, `Xuannd`, `Binhrau1`, `Thuoclao6996`, `danv`, `No1.XS`

**Acceptance query:**

```sql
SELECT username, pick_type, hits, total, win_rate
FROM expert_win_rates
WHERE period_label = '2026-06'
  AND username IN ('himle79','Xuannd','Binhrau1','Thuoclao6996','danv','No1.XS')
  AND pick_type LIKE 'dan_%'
ORDER BY username, pick_type;
```

**Scenario: himle79 dan_40s**
- THEN `total >= 15` (hoặc max days user actually posted)
- AND `abs(win_rate - 0.944) < 0.03` khi so với track record 17/18

**Scenario: User không chốt tháng 6**
- THEN row không tồn tại (không fabricate)

---

## ADDED Requirements

### REQ-DB-001: Period `rolling_90d`

`seed_expert_win_rates.py` SHALL support:

```bash
python scripts/seed_expert_win_rates.py --period rolling_90d [--write-pick-results]
```

Window: `today - 90 days` → `today`, skip Sundays without draw.

**Scenario: API backtest source**
- GIVEN seed rolling_90d complete
- WHEN `GET /forum/experts/backtest?days=90`
- THEN `"source": "db"`, `"period_label": "rolling_90d"`

---

### REQ-DB-002: July topic rollover

Backfill / live crawl SHALL resolve topic tháng 7 khi tháng 6 khóa (extension `thread-discovery` logic).

Tháng 6 backfill v2 **không** thay đổi — chỉ mở rộng coverage tháng 6.

**Scenario: Live ingest tháng 7**
- GIVEN topic `chan-dan-...-thang-7-2026` active
- WHEN extension poll 2026-07-04
- THEN picks ghi `target_date=2026-07-04` (đã có — không regression)

---

### REQ-DB-003: Track record cross-check

File `xsmb_cao_thu_trackrecord.md` là **reference thủ công** cho audit, không phải source of truth runtime.

`audit_expert_winrate.py --compare-trackrecord` SHALL parse bảng dàn 40s/36s và báo:

- `MATCH` — DB rate within ±3% of manual track
- `DRIFT` — lệch >3% (cần investigate parse/backfill)
- `NO_DATA` — DB thiếu rows

**Scenario: himle79**
- GIVEN manual 17/18 = 94%
- WHEN audit sau backfill v2
- THEN status `MATCH` hoặc `DRIFT` with diff printed
