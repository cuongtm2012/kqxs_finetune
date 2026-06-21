from app.services.minhngoc_service import import_mb_from_minhngoc
from app.services.xskt_service import import_mb_from_xskt


def import_mb_day(day_yyyy_mm_dd: str) -> bool:
    """Import one MB draw day; minhngoc first, xskt as fallback."""
    if import_mb_from_minhngoc(day_yyyy_mm_dd):
        return True
    return import_mb_from_xskt(day_yyyy_mm_dd)
