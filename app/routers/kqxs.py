import logging

from fastapi import APIRouter, Query

from app.config import settings
from app.services.kqxs_service import kqxs_service
from app.services.rbk_service import rbk_service
from app.utils.date_util import normalize_ngaychot, normalize_ngaychot_regional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/kqxs", tags=["kqxs"])


@router.get("/chotkq")
def get_chot_kq(
    ngaychot: str = "",
    email: str = "",
    name: str = "",
    skip: int = 0,
    limit: int = 10,
):
    ngaychot = normalize_ngaychot(ngaychot) or ""
    return kqxs_service.get_chot_kq(ngaychot, email, name, skip, limit)


@router.get("/ketqua")
def get_ket_qua(
    ngaychot: str = "",
    skip: int = 0,
    limit: int = 10,
):
    ngaychot = normalize_ngaychot(ngaychot) or ""
    return kqxs_service.get_ket_qua(ngaychot, skip, limit)


@router.get("/trending")
def get_trending(ngaychot: str = ""):
    ngaychot = normalize_ngaychot(ngaychot) or ""
    return kqxs_service.get_trending(ngaychot)


@router.get("/caudep")
def get_caudep(
    ngaychot: str = "",
    limit: int = 0,
    nhay: int = 0,
    lon: int = 0,
):
    ngaychot = normalize_ngaychot(ngaychot) or ""
    return kqxs_service.get_caudep(ngaychot, limit, nhay, lon)


@router.get("/limitday")
def get_limitday(ngaychot: str = ""):
    ngaychot = normalize_ngaychot(ngaychot) or ""
    url = settings.caudep_url % (5, ngaychot, 1, 1)
    return rbk_service.limit_caudep(url)


@router.get("/ketquamn")
def get_ket_qua_mn(ngaychot: str = ""):
    ngaychot = normalize_ngaychot_regional(ngaychot) or ""
    return kqxs_service.get_ket_qua_mn(ngaychot)


@router.get("/ketquamt")
def get_ket_qua_mt(ngaychot: str = ""):
    ngaychot = normalize_ngaychot_regional(ngaychot) or ""
    return kqxs_service.get_ket_qua_mt(ngaychot)
