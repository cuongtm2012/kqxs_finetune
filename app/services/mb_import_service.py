from app.services.minhngoc_service import import_mb_from_minhngoc
from app.services.mketqua_service import import_mb_from_mketqua
from app.services.xskt_service import import_mb_from_xskt


def import_mb_day(day_yyyy_mm_dd: str, *, prefer_mketqua: bool = False) -> bool:
    """Import one MB draw day; mketqua (optional) → minhngoc → xskt."""
    if prefer_mketqua and import_mb_from_mketqua(day_yyyy_mm_dd):
        return True
    if import_mb_from_minhngoc(day_yyyy_mm_dd):
        return True
    return import_mb_from_xskt(day_yyyy_mm_dd)
