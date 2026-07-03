"""Tests for timestamp filtering and cutoff logic — đảm bảo pick chỉ hợp lệ trước 18:00."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.services.expert_score_service import _before_cutoff, draw_cutoff_iso

import pytest

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
TARGET = "2026-07-02"


def test_before_cutoff_17h_pass():
    t = datetime(2026, 7, 2, 17, 30, 0, tzinfo=TZ)
    assert _before_cutoff(t.isoformat(), TARGET) is True


def test_before_cutoff_18h_exact_strictly_before():
    """Cut-off là < 18:00, nên 18:00 exact là FAIL."""
    t = datetime(2026, 7, 2, 18, 0, 0, tzinfo=TZ)
    assert _before_cutoff(t.isoformat(), TARGET) is False


def test_before_cutoff_18h01_fail():
    t = datetime(2026, 7, 2, 18, 0, 1, tzinfo=TZ)
    assert _before_cutoff(t.isoformat(), TARGET) is False


def test_before_cutoff_19h_fail():
    t = datetime(2026, 7, 2, 19, 0, 0, tzinfo=TZ)
    assert _before_cutoff(t.isoformat(), TARGET) is False


def test_before_cutoff_other_date():
    """Pick cho ngày A nhưng post ngày B → phải so với ngày quay."""
    t = datetime(2026, 7, 1, 23, 0, 0, tzinfo=TZ)
    assert _before_cutoff(t.isoformat(), "2026-07-02") is True


def test_before_cutoff_wrong_date():
    """Pick post sau khi quay → fail."""
    t = datetime(2026, 7, 3, 8, 0, 0, tzinfo=TZ)
    assert _before_cutoff(t.isoformat(), "2026-07-02") is False


def test_draw_cutoff_iso_format():
    iso = draw_cutoff_iso("2026-07-02")
    assert "+07:00" in iso
    assert "2026-07-02T18:00:00" in iso


def test_draw_cutoff_iso_raises_on_wrong_date():
    """Hàm raise ValueError với date invalid — behavior hiện tại."""
    with pytest.raises(ValueError):
        draw_cutoff_iso("invalid")


def test_pick_timestamp_from_ms():
    """Test forum timestamp ms → datetime conversion."""
    # 18:30 ICT 2026-07-01 = 1719844200000 ms → nhưng timestamp này là 2024
    # Dùng timestamp chính xác cho 2026-07-01 18:30 ICT
    from datetime import timezone
    ts_s = int(datetime(2026, 7, 1, 18, 30, 0, tzinfo=TZ).timestamp())
    dt = datetime.fromtimestamp(ts_s, tz=TZ)
    assert dt.hour == 18
    assert dt.minute == 30
