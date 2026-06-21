import logging

from fastapi import APIRouter, HTTPException

from app.services.rbk_service import rbk_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rbk", tags=["rbk"])


@router.get("/kqxs")
def import_kqxs():
    days = rbk_service.import_kqxs_days(3)
    return {"status": "ok", "message": "Imported KQXS from xskt", "days": days, "source": "xskt"}


@router.get("/chotkq")
def import_chotkq():
    days = rbk_service.import_chotkq_days(2)
    return {"status": "ok", "message": "Imported chotkq", "days": days}


@router.get("/caudep")
def import_caudep():
    result = rbk_service.import_caudep_full()
    return {
        "status": "ok",
        "message": "Imported caudep",
        "limitday": result["limitday"],
    }


@router.get("/rssmn")
def import_rss_mn():
    try:
        entries = rbk_service.import_rss_mn()
        return {"status": "ok", "message": "Imported XSMN RSS", "entries": entries}
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(status_code=500, detail={"status": "error", "message": str(exc)})


@router.get("/rssmt")
def import_rss_mt():
    try:
        entries = rbk_service.import_rss_mt()
        return {"status": "ok", "message": "Imported XSMT RSS", "entries": entries}
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(status_code=500, detail={"status": "error", "message": str(exc)})
