import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.services.rbk_service import rbk_service
from app.utils.date_util import today_yyyy_mm_dd

logger = logging.getLogger(__name__)


def _import_kqxs_today():
    from app.repositories.draw_repo import draw_repo
    from app.services.mb_import_service import import_mb_day

    day = today_yyyy_mm_dd()
    if import_mb_day(day):
        draw_repo.refresh_loto_view()
        from app.services.stats_service import clear_stats_cache

        clear_stats_cache()
        logger.info("Scheduled XSMB import finished for %s", day)
    else:
        logger.warning("Scheduled XSMB import failed for %s", day)


def _import_chotkq_today():
    day = today_yyyy_mm_dd()
    url = settings.chotkq % day
    rbk_service.als_chot_kq(url, day)


def _import_trend_today():
    day = today_yyyy_mm_dd()
    url = settings.trend_url % day
    rbk_service.als_trend(url, day)


def _import_caudep_scheduled():
    rbk_service.import_caudep_full(max_limit=16)


def _import_rss_mn():
    rbk_service.import_rss_mn()


def _import_rss_mt():
    rbk_service.import_rss_mt()


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _import_kqxs_today,
        CronTrigger(minute="15-31", hour=18),
        id="kqxs",
        replace_existing=True,
    )
    scheduler.add_job(
        _import_chotkq_today,
        CronTrigger(minute="25,55"),
        id="chotkq",
        replace_existing=True,
    )
    scheduler.add_job(
        _import_trend_today,
        CronTrigger(minute="20,50"),
        id="trending",
        replace_existing=True,
    )
    scheduler.add_job(
        _import_caudep_scheduled,
        CronTrigger(hour=20, minute=0),
        id="caudep",
        replace_existing=True,
    )
    scheduler.add_job(
        _import_rss_mn,
        CronTrigger(hour=19, minute=0),
        id="rssmn",
        replace_existing=True,
    )
    scheduler.add_job(
        _import_rss_mt,
        CronTrigger(hour=19, minute=0),
        id="rssmt",
        replace_existing=True,
    )
    return scheduler
