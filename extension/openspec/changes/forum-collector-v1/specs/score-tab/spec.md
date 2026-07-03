# Spec Delta: Score Tab (Kết quả)

## ADDED Requirements

### REQ-ST-001: Tab Kết quả

Popup SHALL có tab **Kết quả** đối chiếu pick cao thủ với KQXS XSMB.

Endpoints (`score-api.ts`):
- `GET /forum/score?target_date=YYYY-MM-DD`
- `POST /forum/score/run?target_date=YYYY-MM-DD` (import mketqua + chấm lại)

Ngày quay hiển thị:
- Trước 18:31 ICT → ngày hôm qua (`getLatestDrawScoreDate`)
- Từ 18:31 → hôm nay
- Nếu `not_scored` → fallback thử ngày trước đó

Chỉ tính pick có `posted_at < 18:00` ICT (cutoff hiển thị trong UI).

**Scenario: Chưa chấm**
- THEN bảng message + nút Tải kết quả / Chấm lại (mketqua)

**Scenario: Đã chấm**
- THEN hiển thị đề, giải ĐB, tổng trúng/tổng, bảng từng cao thủ (TRÚNG/trượt)

Backend cron 18:31 ICT gọi `run_daily_settlement()` (`app/scheduler.py`).
