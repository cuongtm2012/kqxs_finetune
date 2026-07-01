# Spec Delta: June 2026 Backfill

## ADDED Requirements

### REQ-JB-001: Backfill CLI

Script `scripts/backfill_forum_picks_month.py` SHALL ingest picks lịch sử theo tháng.

```bash
python scripts/backfill_forum_picks_month.py --month 2026-06 [--dry-run] [--skip-existing]
```

**Output:** summary JSON stdout:
```json
{
  "month": "2026-06",
  "days_attempted": 26,
  "days_ingested": 22,
  "days_skipped_sunday": 4,
  "days_skipped_no_thread": 2,
  "pick_rows_total": 142,
  "errors": []
}
```

---

### REQ-JB-002: Ngày trong tháng 6

Với `--month 2026-06`:

| Rule | Hành vi |
|------|---------|
| Chủ nhật | Skip (không quay XSMB) |
| Thứ 2–Thứ 7 | `target_date = YYYY-MM-DD` |
| Cửa sổ pick | `D-1 18:30` → `D 18:00` ICT |

**Scenario: Chủ nhật 2026-06-07**
- WHEN backfill tháng 6
- THEN không ingest `target_date=2026-06-07`

**Scenario: Thứ 2 2026-06-02**
- WHEN backfill
- THEN ingest picks trong cửa sổ `2026-06-01 18:30` → `2026-06-02 18:00`

---

### REQ-JB-003: Thread sources tháng 6

Backfill SHALL crawl:

**Chăn nuôi (topic tháng 6 — cố định):**

| Key | Thread slug (forumketqua.net) |
|-----|-------------------------------|
| stl_k2n | `nuoi-song-thu-lo-khung-2-ngay-thang-6-2026.101198` |
| btl_k3n | `topic-chan-nuoi-xsmb-btl-k3n-thang-6-2026.101208` |
| btl_k5n | `topic-chan-nuoi-xsmb-btl-k5n-thang-6-2026.101183` |
| dan_40s | `chan-dan-dac-biet-xsmb-40s-khung-4-thang-6-2026.101212` |
| dan_64s | `dan-dac-biet-xsmb-64s-thang-6-2026.101209` |

**Theo ngày D:**

| Forum | Discovery |
|-------|-----------|
| `thao_luan` | Listing + title match `THẢO LUẬN.*DD/MM/YYYY` hoặc `KNOWN_DAILY_IDS` |
| `mo_bat` | Listing + title match `MỞ BÁT.*DD/MM/YYYY` |

**Known daily IDs (ưu tiên — đã verify):**

| Date | Thread slug |
|------|-------------|
| 2026-06-22 | `thao-luan-du-doan-xsmb-thu-2-ngay-22-6-2026.101326` |
| 2026-06-23 | `thao-luan-du-doan-xsmb-thu-3-ngay-23-6-2026.101331` |
| 2026-06-24 | `thao-luan-du-doan-xsmb-thu-4-ngay-24-6-2026.101336` |
| 2026-06-25 | `thao-luan-du-doan-xsmb-thu-5-ngay-25-6-2026.101341` |
| 2026-06-26 | `thao-luan-du-doan-xsmb-thu-6-ngay-26-6-2026.101347` |
| 2026-06-27 | `thao-luan-du-doan-xsmb-thu-7-ngay-27-6-2026.101352` |

Ngày 1–21: discover từ listing (cùng logic extension `discoverDailyThread`).

---

### REQ-JB-004: Ingest format

Mỗi ngày D, backfill SHALL build payload tương thích `ingest_collect_session`:

```json
{
  "target_date": "2026-06-22",
  "window_start": "2026-06-21T18:30:00+07:00",
  "window_end": "2026-06-22T18:00:00+07:00",
  "posts": { "post_id": { "user", "forum", "posted_at_ms", "picks", ... } },
  "summary": { ... }
}
```

Gọi `forum_repo` trực tiếp hoặc `ingest_collect_session()` — kết quả giống extension sync.

**Scenario: Idempotent**
- GIVEN `--skip-existing` và session `2026-06-22` đã có
- WHEN backfill lại
- THEN skip ngày đó, không duplicate rows

---

### REQ-JB-005: Pick parsing

Parser SHALL tái sử dụng logic từ:
- `scripts/crawl_forum_picks.py` (regex STL/BTL/de/dàn)
- Hoặc extension `pick-parser.ts` (parity test khuyến nghị)

Pick types output: `stl`, `btl`, `de_cham`, `de_tong`, `de_dau`, `dan_40s`, `dan_36s`, `dan_64s`, `dan_de`, `muc_lo`.

**Scenario: Dàn 40s từ topic chăn nuôi**
- GIVEN post trong thread `dan_40s` với ≥38 số
- THEN `pick_type = dan_40s` (infer từ title + count)

---

### REQ-JB-006: Seed win rate sau backfill

Sau backfill tháng 6, operator SHALL chạy:

```bash
python scripts/seed_expert_win_rates.py --period 2026-06 --write-pick-results
```

**Scenario: End-to-end tháng 6**
- GIVEN backfill hoàn tất, draws có sẵn
- WHEN seed win rates
- THEN `SELECT COUNT(*) FROM expert_win_rates WHERE period_label='2026-06'` > 0

---

### REQ-JB-007: Verification queries

Document SQL verify trong README/tasks:

```sql
-- Picks tháng 6
SELECT target_date, COUNT(*) FROM forum_user_picks
WHERE target_date >= '2026-06-01' AND target_date < '2026-07-01'
GROUP BY 1 ORDER BY 1;

-- Win rate top cao thủ
SELECT username, pick_type, hits, total, win_rate
FROM expert_win_rates WHERE period_label = '2026-06'
ORDER BY win_rate DESC, total DESC LIMIT 20;
```

**Scenario: Audit nhcsxh**
- GIVEN alias `LOKHATA 1789` → `nhcsxh`
- THEN win rate `nhcsxh` không bị inflate do 2 tài khoản
