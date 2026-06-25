import logging
import math
import random
import time
from collections import defaultdict
from datetime import date, timedelta
from typing import Callable, Literal, Optional

from app.data.max_cycle_history import load_max_cycle_history
from app.db import fetch_all
from app.prediction.constants import DEFAULT_TOP, TARGET_DE, TARGET_LOTO
from app.prediction.features import FeatureContext, actual_values_for_date, latest_draw_date, previous_draw_date
from app.prediction.models import bayesian_update, chi_square
from app.repositories.candidate_repo import candidate_repo
from app.services.stats_service import (
    CANDIDATES_DISCLAIMER,
    WEEKDAYS_VI,
    approaching_max_cycle_matches,
    calendar_bias_matches,
    conditional_frequency_matches,
    de_calendar_matches,
    de_lag1_matches,
    de_loto_boost_matches,
    de_digit_trend_matches,
    de_frequency_rank_hot_matches,
    de_frequency_trend_matches,
    frequency_hot_matches,
    frequency_rank_hot_matches,
    frequency_trend_matches,
    gap_hot_matches,
    get_conditional_frequency,
    get_day_context,
    get_loto_frequency_summary,
    get_loto_frequency_trend,
    get_de_frequency_summary,
    get_de_frequency_trend,
    get_de_digit_trend,
    get_lo_roi,
    get_pairs,
)
from app.services.rbk_crawler import rbk_cau_loto_matches

logger = logging.getLogger(__name__)

CandidateSort = Literal["score", "filters", "loto"]
CandidateTarget = Literal["loto", "de"]
FilterMatch = tuple[str, str, Optional[dict]]

DE_TARGET_WARNING = (
    "Đề chỉ 1 sample/ngày — noise cao. Backtest thường dưới random. "
    "Chỉ dùng tham khảo, không kỳ vọng beat baseline >12%."
)

DE_FILTER_PRIORITY = {
    "de-intersection": 5,
    "de-cf": 4,
    "de-cond-prev": 4,
    "de-frequency-trend": 4,
    "de-digit-trend": 3,
    "de-loto-boost": 3,
    "de-chi-square": 3,
    "de-bayesian-update": 3,
    "cond-freq-de": 3,
    "de-frequency-rank": 2,
    "de-lag1": 2,
    "de-calendar": 1,
}

LO_ROI_SCORE_CAP = 0.5
DE_MAX_MIN_FILTERS = 2
MAX_CYCLE_MIN_PCT = 40
GAP_HOT_MIN_GAP = 8
CYCLE_HISTORY_MIN_RATIO = 0.50
CYCLE_HISTORY_MIN_GAP = 10
FREQUENCY_HOT_MIN_LIFT = 1.05
FREQ_RANK_TOP_N = 25
FREQ_TREND_MIN_MOMENTUM = 3.0
DE_FREQ_RANK_TOP_N = 15
DE_FREQ_TREND_MIN_MOMENTUM = 0.8
DE_DIGIT_TREND_MIN_MOMENTUM = 2.0
PREDICTION_MODEL_TOP_N = 40
CHI_SQUARE_MIN_SCORE = 0.60
BAYESIAN_UPDATE_MIN_SCORE = 0.50
COND_FREQ_LOTO_MIN_LIFT = 2.0
COND_FREQ_LOTO_MIN_OCC = 3
COND_FREQ_DE_MIN_LIFT = 3.0
COND_FREQ_DE_MIN_OCC = 2
DE_COND_PREV_MIN_LIFT = 2.0
SAME_DATE_MIN_LIFT = 1.5


def _score_contribution(filter_key: str, detail: dict) -> float:
    lift = float(detail.get("lift", 1))
    if filter_key in ("lag-1", "same-day"):
        return min((lift - 1) * 2, 0.5)
    if filter_key == "max-cycle":
        return detail.get("pct_of_max", 0) / 100.0
    if filter_key == "gap-hot":
        return min(detail.get("current_gap", 0) / 25.0, 0.5)
    if filter_key == "cycle-history":
        gap_ratio = float(detail.get("gap_ratio", 0.5))
        return min(gap_ratio * 0.5, 0.5)
    if filter_key == "frequency-hot":
        return min((float(detail.get("lift", 1)) - 1) * 2, 0.4)
    if filter_key == "frequency-rank":
        return min((float(detail.get("lift", 1)) - 1) * 2, 0.5)
    if filter_key == "frequency-trend":
        momentum = float(detail.get("momentum_pp", detail.get("momentum", 0)))
        return min(momentum / 20.0, 0.5)
    if filter_key in ("calendar", "de-calendar"):
        return min((lift - 1) * 3, 0.5)
    if filter_key == "lo-roi":
        return min((lift - 1) * 1, LO_ROI_SCORE_CAP)
    if filter_key == "de-lag1":
        return min((lift - 1) * 3, 0.5)
    if filter_key == "de-loto-boost":
        return min((lift - 1) * 2, 0.3)
    if filter_key == "de-intersection":
        cf_lift = float(detail.get("cf_lift", detail.get("lift", 1)))
        rbk_cau = int(detail.get("rbk_cau", 0))
        return min((cf_lift - 1) * 2, 0.6) + min(rbk_cau / 8.0, 0.5)
    if filter_key == "de-cf":
        return min((lift - 1) * 2, 0.5)
    if filter_key == "de-frequency-rank":
        return min((float(detail.get("lift", 1)) - 1) * 2, 0.5)
    if filter_key == "de-frequency-trend":
        momentum = float(detail.get("momentum_pp", detail.get("momentum", 0)))
        return min(momentum / 15.0, 0.5)
    if filter_key == "de-digit-trend":
        momentum = float(detail.get("momentum_pp", detail.get("momentum", 0)))
        return min(momentum / 20.0, 0.4)
    if filter_key == "cond-freq-loto":
        return min((lift - 1) * 0.5, 0.6)
    if filter_key == "cond-freq-de":
        return min((lift - 1) * 0.3, 0.7)
    if filter_key == "de-cond-prev":
        return min((lift - 1) * 0.5, 0.8)
    if filter_key == "same-date":
        return min((lift - 1) * 0.3, 0.5)
    if filter_key in ("rbk-cau", "rbk-cau-no-loan"):
        return min(float(detail.get("weight", 0)) * 0.5, 0.5)
    if filter_key in ("chi-square", "de-chi-square"):
        z = float(detail.get("z", 0))
        return min(max(z, 0) / 5.0, 0.5)
    if filter_key in ("bayesian-update", "de-bayesian-update"):
        lift = float(detail.get("lift", 1))
        return min((lift - 1) * 2, 0.5)
    if filter_key == "cycle-boost":
        btype = detail.get("type", "")
        if btype == "dao":
            return 0.15  # số đảo: boost nhẹ
        if btype == "cham":
            return 0.08  # cham trùng: boost nhẹ
        if btype == "bong":
            return 0.10  # bóng dương: boost vừa
        return 0.05
    return 0.0


def _compute_score(breakdown: dict[str, float]) -> float:
    return round(sum(breakdown.values()), 2)


def _resolve_dates(target_date: Optional[str]) -> tuple[str, str]:
    latest = latest_draw_date()
    if latest is None:
        raise ValueError("No MB draw data available")

    if target_date:
        target = date.fromisoformat(target_date)
        as_of = previous_draw_date(target)
        if as_of is None:
            as_of = latest
    else:
        as_of = latest
        target = as_of + timedelta(days=1)

    return target.isoformat(), as_of.isoformat()


def _lag1_matches(yesterday_lotos: set[str], min_lift: float = 1.10) -> list[FilterMatch]:
    result = get_pairs(pair_type="lag-1", min_lift=min_lift, min_occ=30, limit=500, sort="lift")
    total_days = result["params"]["total_days"]
    matches: list[FilterMatch] = []
    seen: set[str] = set()

    for row in result["data"]:
        x, y = row["x"], row["y"]
        if x in yesterday_lotos and y not in seen:
            reason = (
                f"lag-1: {x} hôm qua → {y} có P={row['p_xy']:.1%} "
                f"(lift {row['lift']}x, baseline {row['baseline']:.1%})"
            )
            detail = {**row, "from_loto": x, "total_days": total_days}
            matches.append((y, reason, detail))
            seen.add(y)
        if y in yesterday_lotos and x not in seen:
            reason = (
                f"lag-1: {y} hôm qua → {x} có P={row['p_xy']:.1%} "
                f"(lift {row['lift']}x, baseline {row['baseline']:.1%})"
            )
            detail = {**row, "from_loto": y, "total_days": total_days}
            matches.append((x, reason, detail))
            seen.add(x)
    return matches


def _same_day_matches(yesterday_lotos: set[str], min_lift: float = 1.10) -> list[FilterMatch]:
    result = get_pairs(pair_type="same-day", min_lift=min_lift, min_occ=30, limit=500, sort="lift")
    total_days = result["params"]["total_days"]
    matches: list[FilterMatch] = []
    seen: set[str] = set()

    for row in result["data"]:
        x, y = row["x"], row["y"]
        if x in yesterday_lotos and y not in seen:
            reason = (
                f"same-day: ({x},{y}) cùng về {row['co_occurrences']}/{total_days} ngày "
                f"(lift {row['lift']}x)"
            )
            matches.append((y, reason, row))
            seen.add(y)
        if y in yesterday_lotos and x not in seen:
            reason = (
                f"same-day: ({x},{y}) cùng về {row['co_occurrences']}/{total_days} ngày "
                f"(lift {row['lift']}x)"
            )
            matches.append((x, reason, row))
            seen.add(x)
    return matches


def _max_cycle_matches(min_pct: int = MAX_CYCLE_MIN_PCT) -> list[FilterMatch]:
    matches: list[FilterMatch] = []
    for lot, summary in approaching_max_cycle_matches(min_pct=min_pct).items():
        reason = (
            f"max-cycle: current gap {summary['current_gap']}/{summary['max_gap_hist']} ngày "
            f"({summary['pct_of_max']}%)"
        )
        matches.append((lot, reason, summary))
    return matches


def _gap_hot_matches(min_gap: int = GAP_HOT_MIN_GAP) -> list[FilterMatch]:
    matches: list[FilterMatch] = []
    for lot, summary in gap_hot_matches(min_gap=min_gap).items():
        reason = (
            f"gap-hot: loto {lot} gan {summary['current_gap']} ngày "
            f"(max hist {summary['max_gap_hist']}, {summary['pct_of_max']}% max cycle)"
        )
        matches.append((lot, reason, summary))
    return matches


def _cycle_history_matches(
    as_of_date: str,
    min_ratio: float = CYCLE_HISTORY_MIN_RATIO,
    min_gap: int = CYCLE_HISTORY_MIN_GAP,
) -> list[FilterMatch]:
    """Match lotos at >= min_ratio of mketqua historical max cycle."""
    _ = as_of_date  # gap summaries use latest draw in DB
    history = load_max_cycle_history()
    if not history:
        return []

    matches: list[FilterMatch] = []
    for lot, summary in gap_hot_matches(min_gap=min_gap).items():
        entry = history.get(lot)
        if not entry:
            continue
        max_gap = int(entry.get("max_gap_days", 0))
        if max_gap <= 0:
            continue
        current_gap = int(summary.get("current_gap", 0))
        if current_gap <= 0:
            continue
        gap_ratio = current_gap / max_gap
        if gap_ratio < min_ratio:
            continue
        gap_ratio_clamped = min(max(gap_ratio, 0.5), 1.0)
        lift = round(1.0 + gap_ratio_clamped * 0.5, 3)
        reason = (
            f"cycle-history: loto {lot} gap {current_gap}/{max_gap} ngày "
            f"(ratio {gap_ratio:.0%}, lift {lift}x, mketqua max)"
        )
        detail = {
            "gap_ratio": round(gap_ratio_clamped, 3),
            "current_gap": current_gap,
            "max_gap": max_gap,
            "max_gap_start": entry.get("max_gap_start"),
            "max_gap_end": entry.get("max_gap_end"),
            "lift": lift,
        }
        matches.append((lot, reason, detail))
    return matches


def _frequency_hot_matches(min_lift: float = FREQUENCY_HOT_MIN_LIFT) -> list[FilterMatch]:
    matches: list[FilterMatch] = []
    for lot, info in frequency_hot_matches(min_lift=min_lift).items():
        reason = (
            f"frequency-hot: loto {lot} xuất hiện {info['freq_pct']:.1f}% ngày "
            f"(lift {info['lift']}x vs baseline {info['baseline']:.1%})"
        )
        matches.append((lot, reason, info))
    return matches


def _frequency_rank_matches(top_n: int = FREQ_RANK_TOP_N) -> list[FilterMatch]:
    matches: list[FilterMatch] = []
    for lot, info in frequency_rank_hot_matches(top_n=top_n).items():
        reason = (
            f"frequency-rank: loto {lot} top {top_n} hay về "
            f"{info['count']}/{info['window_days']} ngày (window {info['rank_window']}d, "
            f"lift {info['lift']}x)"
        )
        matches.append((lot, reason, info))
    return matches


def _frequency_trend_matches(min_momentum: float = FREQ_TREND_MIN_MOMENTUM) -> list[FilterMatch]:
    matches: list[FilterMatch] = []
    for lot, info in frequency_trend_matches(min_momentum_pp=min_momentum).items():
        short = info["short_window"]
        long = info["long_window"]
        w = info["windows"]
        short_rate = w.get(str(short), {}).get("rate_pct", 0)
        long_rate = w.get(str(long), {}).get("rate_pct", 0)
        reason = (
            f"frequency-trend: {lot} đang nóng lên +{info['momentum_pp']}pp "
            f"({short}d {short_rate}% vs {long}d {long_rate}%)"
        )
        matches.append((lot, reason, info))
    return matches


def _de_frequency_rank_matches(top_n: int = DE_FREQ_RANK_TOP_N) -> list[FilterMatch]:
    matches: list[FilterMatch] = []
    for de, info in de_frequency_rank_hot_matches(top_n=top_n).items():
        reason = (
            f"de-frequency-rank: đề {de} hot {info['rank_window']}d "
            f"({info['count']} lần, lift {info['lift']}x, đầu {info['dau']} tổng {info['tong']})"
        )
        matches.append((de, reason, info))
    return matches


def _de_frequency_trend_matches(min_momentum: float = DE_FREQ_TREND_MIN_MOMENTUM) -> list[FilterMatch]:
    matches: list[FilterMatch] = []
    for de, info in de_frequency_trend_matches(min_momentum_pp=min_momentum).items():
        short = info["short_window"]
        long = info["long_window"]
        w = info["windows"]
        short_rate = w.get(str(short), {}).get("rate_pct", 0)
        long_rate = w.get(str(long), {}).get("rate_pct", 0)
        tag = "stable-hot" if info.get("stable_hot") else f"+{info['momentum_pp']}pp"
        reason = (
            f"de-frequency-trend: đề {de} {tag} "
            f"({short}d {short_rate}% vs {long}d {long_rate}%, đầu {info['dau']} tổng {info['tong']})"
        )
        matches.append((de, reason, info))
    return matches


def _de_digit_trend_matches(min_momentum: float = DE_DIGIT_TREND_MIN_MOMENTUM) -> list[FilterMatch]:
    matches: list[FilterMatch] = []
    for de, info in de_digit_trend_matches(min_momentum_pp=min_momentum).items():
        signals = ", ".join(info.get("digit_signals", []))
        reason = f"de-digit-trend: đề {de} — {signals}"
        matches.append((de, reason, info))
    return matches


def _calendar_matches(weekday: int, min_lift: float = 1.05) -> list[FilterMatch]:
    matches: list[FilterMatch] = []
    for lot, info in calendar_bias_matches(weekday, min_lift=min_lift).items():
        reason = (
            f"calendar: {info['weekday'].lower()} loto {lot} tần suất {info['prob']:.1%} "
            f"(lift {info['lift']}x)"
        )
        matches.append((lot, reason, info))
    return matches


def _lo_roi_matches(yesterday_de: str, window: int = 3) -> list[FilterMatch]:
    if not yesterday_de:
        return []
    result = get_lo_roi(de=yesterday_de, window=window, limit=200)
    matches: list[FilterMatch] = []
    for row in result["data"]:
        if row["lift"] <= 1.05:
            continue
        if row["prob"] < 0.15:
            continue
        reason = (
            f"lô rơi: sau đề {yesterday_de} loto {row['loto']} rơi {row['prob']:.1%} "
            f"(lift {row['lift']}x)"
        )
        matches.append((row["loto"], reason, row))
    return matches


def _dict_to_matches(
    data: dict[str, dict],
    reason_fn: Callable[[str, dict], str],
) -> list[FilterMatch]:
    return [(key, reason_fn(key, info), info) for key, info in data.items()]


def _de_lag1_filter_matches(yesterday_de: str) -> list[FilterMatch]:
    return _dict_to_matches(
        de_lag1_matches(yesterday_de, min_lift=1.05),
        lambda de_val, info: (
            f"de-lag1: đề {info['from_de']} hôm qua → {de_val} có P={info['p_xy']:.1%} "
            f"(lift {info['lift']}x)"
        ),
    )


def _de_calendar_filter_matches(weekday: int) -> list[FilterMatch]:
    return _dict_to_matches(
        de_calendar_matches(weekday, min_lift=1.05),
        lambda de_val, info: (
            f"de-calendar: {info['weekday'].lower()} đề {de_val} tần suất {info['prob']:.1%} "
            f"(lift {info['lift']}x)"
        ),
    )


def _de_loto_boost_filter_matches(yesterday_lotos: set[str]) -> list[FilterMatch]:
    return _dict_to_matches(
        de_loto_boost_matches(yesterday_lotos, min_lift=1.05),
        lambda lot, info: (
            f"de-loto-boost: loto {lot} về hôm qua, đề {lot} có P={info['prob']:.1%} "
            f"(lift {info['lift']}x)"
        ),
    )


def _de_intersection_filter_matches(target_date: str) -> list[FilterMatch]:
    from app.services.intersection_service import build_intersection

    result = build_intersection(target_date=target_date)
    cf_by = {row["loto"]: row for row in result["cf_candidates"]}
    pick_by = {row["loto"]: row for row in result["final_picks"]}
    matches: list[FilterMatch] = []
    for lot in result["intersection"]:
        cf = cf_by.get(lot, {})
        pick = pick_by.get(lot, {})
        cf_lift = cf.get("lift") or pick.get("cf_lift", 1)
        rbk_cau = pick.get("rbk_cau", 0)
        detail = {
            "loto": lot,
            "cf_lift": cf_lift,
            "rbk_cau": rbk_cau,
            "lift": cf_lift,
            "yesterday_db": result["yesterday_db"],
        }
        reason = (
            f"de-intersection: CF∩RBK sau đề {result['yesterday_db']} → {lot} "
            f"(CF lift {cf_lift}x, RBK {rbk_cau} cầu)"
        )
        matches.append((lot, reason, detail))
    return matches


def _de_cf_filter_matches(yesterday_de: str, weekday: int) -> list[FilterMatch]:
    return _dict_to_matches(
        conditional_frequency_matches(yesterday_de, target_weekday=weekday, min_lift=3.0),
        lambda lot, info: (
            f"de-cf: sau ĐB {info['db_loto']} → đề {lot} "
            f"{info['count']}/{info['total_samples']} (lift {info['lift']}x)"
        ),
    )


def _cond_freq_loto_matches(
    yesterday_de: str,
    min_lift: float = COND_FREQ_LOTO_MIN_LIFT,
    min_occ: int = COND_FREQ_LOTO_MIN_OCC,
) -> list[FilterMatch]:
    if not yesterday_de:
        return []
    result = get_conditional_frequency(
        db_loto=yesterday_de,
        target_weekday=None,
        min_occ=min_occ,
        limit=20,
        sort="lift",
    )
    matches: list[FilterMatch] = []
    for row in result["loto_frequency"]:
        if row["lift"] < min_lift:
            continue
        reason = (
            f"cond-freq-loto: sau đề {yesterday_de} loto {row['loto']} "
            f"về {row['count']}/{result['total_samples']} lần "
            f"(lift {row['lift']:.2f}x)"
        )
        matches.append(
            (
                row["loto"],
                reason,
                {
                    "lift": row["lift"],
                    "occurrences": row["count"],
                    "total_samples": result["total_samples"],
                },
            )
        )
    return matches


def _cond_freq_de_matches(
    yesterday_de: str,
    min_lift: float = COND_FREQ_DE_MIN_LIFT,
    min_occ: int = COND_FREQ_DE_MIN_OCC,
) -> list[FilterMatch]:
    if not yesterday_de:
        return []
    result = get_conditional_frequency(
        db_loto=yesterday_de,
        target_weekday=None,
        min_occ=min_occ,
        limit=20,
        sort="lift",
    )
    matches: list[FilterMatch] = []
    for row in result["loto_frequency"]:
        if row["lift"] < min_lift:
            continue
        reason = (
            f"cond-freq-de: sau đề {yesterday_de} đề {row['loto']} "
            f"về {row['count']}/{result['total_samples']} lần "
            f"(lift {row['lift']:.2f}x)"
        )
        matches.append(
            (
                row["loto"],
                reason,
                {
                    "lift": row["lift"],
                    "occurrences": row["count"],
                    "total_samples": result["total_samples"],
                },
            )
        )
    return matches


def _de_cond_prev_matches(
    yesterday_de: str,
    min_lift: float = DE_COND_PREV_MIN_LIFT,
    min_occ: int = 2,
) -> list[FilterMatch]:
    if not yesterday_de:
        return []
    result = get_conditional_frequency(
        db_loto=yesterday_de,
        target_weekday=None,
        min_occ=min_occ,
        limit=10,
        sort="lift",
    )
    matches: list[FilterMatch] = []
    for row in result["loto_frequency"]:
        if row["lift"] < min_lift:
            continue
        reason = (
            f"de-cond-prev: đề {yesterday_de}→{row['loto']} "
            f"{row['count']} lần (lift {row['lift']:.1f}x)"
        )
        matches.append(
            (
                row["loto"],
                reason,
                {
                    "lift": row["lift"],
                    "occurrences": row["count"],
                    "total_samples": result["total_samples"],
                },
            )
        )
    return matches


def _same_date_matches(
    target_date: str,
    min_lift: float = SAME_DATE_MIN_LIFT,
) -> list[FilterMatch]:
    dt = date.fromisoformat(target_date)
    rows = fetch_all(
        """
        SELECT p.last_two AS loto, COUNT(*) AS cnt
        FROM draws d
        JOIN prizes p ON p.draw_id = d.id
        WHERE d.region = 'MB'
          AND EXTRACT(MONTH FROM d.draw_date) = %s
          AND EXTRACT(DAY FROM d.draw_date) = %s
          AND d.draw_date < %s::date
          AND p.prize_level = 'DB'
        GROUP BY p.last_two
        ORDER BY cnt DESC
        """,
        (dt.month, dt.day, target_date),
    )
    if not rows:
        return []

    total = sum(int(r["cnt"]) for r in rows)
    matches: list[FilterMatch] = []
    for row in rows:
        cnt = int(row["cnt"])
        lift = (cnt / total) / 0.01 if total else 0.0
        if lift < min_lift:
            continue
        reason = (
            f"same-date: ngày {dt.month}/{dt.day} lịch sử "
            f"{row['loto']} về {cnt}/{total} lần (lift {lift:.1f}x)"
        )
        matches.append(
            (
                row["loto"],
                reason,
                {
                    "lift": round(lift, 2),
                    "occurrences": cnt,
                    "total_years": total,
                },
            )
        )
    return matches


def _rbk_cau_filter_matches(as_of_date: str) -> list[FilterMatch]:
    return _dict_to_matches(
        rbk_cau_loto_matches(as_of_date, limit=5, min_cau=1, lon=0, nhay=1),
        lambda lot, info: (
            f"rbk-cau: {lot} có {info['cau_count']} cầu RBK (không lộn, weight {info['weight']})"
        ),
    )


def _rbk_cau_no_loan_filter_matches(as_of_date: str) -> list[FilterMatch]:
    return _dict_to_matches(
        rbk_cau_loto_matches(as_of_date, limit=5, min_cau=1, lon=1, nhay=1),
        lambda lot, info: (
            f"rbk-cau-no-loan: {lot} có {info['cau_count']} cầu RBK (lộn, weight {info['weight']})"
        ),
    )


def _feature_ctx(as_of_date: str, target_date: str, target_type: str) -> FeatureContext:
    return FeatureContext.load(
        date.fromisoformat(as_of_date),
        target_type,
        date.fromisoformat(target_date),
        use_cache=True,
    )


# Bóng dương mapping: 0→5, 1→6, 2→7, 3→8, 4→9, 5→0, 6→1, 7→2, 8→3, 9→4
BONG_DUONG = {"0": "5", "1": "6", "2": "7", "3": "8", "4": "9", "5": "0", "6": "1", "7": "2", "8": "3", "9": "4"}


def _cycle_boost_matches(yesterday_de: str) -> list[FilterMatch]:
    """Boost numbers with cham trùng (đuôi đề hôm qua) + số đảo + bóng dương."""
    if not yesterday_de:
        return []
    matches: list[FilterMatch] = []
    seen = set()

    # 1. Cham trùng: số có đầu hoặc đuôi trùng với đuôi đề hôm qua
    last_digit = yesterday_de[-1]
    for tens in range(10):
        for units in range(10):
            val = f"{tens}{units}"

    # 2. Số đảo: YX từ XY (đề hôm qua)
    rev_de = yesterday_de[1] + yesterday_de[0]
    if rev_de not in seen:
        seen.add(rev_de)
        matches.append((rev_de, f"cycle-boost: số đảo {yesterday_de}→{rev_de}", {"lift": 1.27, "type": "dao"}))

    # 3. Cham trùng: số có đầu hoặc đuôi = đuôi đề
    for val in [f"{d}{u}" for d in range(10) for u in range(10)]:
        if val in seen:
            continue
        if val[0] == last_digit or val[1] == last_digit:
            seen.add(val)
            matches.append((val, f"cycle-boost: cham {last_digit} (đuôi đề {yesterday_de})", {"lift": 1.05, "type": "cham"}))

    # 4. Bóng dương: số có tổng = bóng dương của tổng đề
    de_sum = str((int(yesterday_de[0]) + int(yesterday_de[1])) % 10)
    bong_sum = BONG_DUONG.get(de_sum)
    if bong_sum:
        for val in [f"{d}{u}" for d in range(10) for u in range(10)]:
            if val in seen:
                continue
            if str((int(val[0]) + int(val[1])) % 10) == bong_sum:
                seen.add(val)
                matches.append((val, f"cycle-boost: bóng dương tổng {de_sum}→{bong_sum}", {"lift": 1.10, "type": "bong"}))

    return matches


def _chi_square_matches(
    as_of_date: str,
    target_date: str,
    target_type: str,
    top_n: int = PREDICTION_MODEL_TOP_N,
    min_score: float = CHI_SQUARE_MIN_SCORE,
) -> list[FilterMatch]:
    ctx = _feature_ctx(as_of_date, target_date, target_type)
    scores = chi_square.score_chi_square(ctx)
    hits = ctx.hit_counts()
    total = sum(hits.values())
    n = len(ctx.universe)
    expected = total / n if n else 0.0

    matches: list[FilterMatch] = []
    for lot, score in sorted(scores.items(), key=lambda x: (-x[1], x[0]))[:top_n]:
        if score < min_score:
            continue
        obs = hits.get(lot, 0)
        z = (obs - expected) / math.sqrt(expected) if expected > 0 else 0.0
        lift = obs / expected if expected > 0 else 1.0
        label = "đề" if target_type == TARGET_DE else "loto"
        reason = (
            f"chi-square: {label} {lot} z={z:.2f} "
            f"(obs={obs}, expected={expected:.1f}, lift {lift:.2f}x, score {score:.2f})"
        )
        matches.append((lot, reason, {"lift": round(lift, 3), "z": round(z, 2), "score": score}))
    return matches


def _bayesian_update_matches(
    as_of_date: str,
    target_date: str,
    target_type: str,
    top_n: int = PREDICTION_MODEL_TOP_N,
    min_score: float = BAYESIAN_UPDATE_MIN_SCORE,
) -> list[FilterMatch]:
    ctx = _feature_ctx(as_of_date, target_date, target_type)
    scores = bayesian_update.score_bayesian_update(ctx)
    hits = ctx.hit_counts()
    total_opp = ctx.total_opportunities
    if total_opp:
        prior = {v: hits.get(v, 0) / total_opp for v in ctx.universe}
    else:
        prior = {v: 1.0 / len(ctx.universe) for v in ctx.universe}

    matches: list[FilterMatch] = []
    for lot, score in sorted(scores.items(), key=lambda x: (-x[1], x[0]))[:top_n]:
        if score < min_score:
            continue
        p = prior.get(lot, 1e-6)
        lift = max(score / 0.5, 1.0) if p > 0 else 1.0
        label = "đề" if target_type == TARGET_DE else "loto"
        reason = (
            f"bayesian-update: {label} {lot} posterior score {score:.2f} "
            f"(windows 7/14/30/60d, prior {p:.3f}, lift {lift:.2f}x)"
        )
        matches.append((lot, reason, {"lift": round(lift, 3), "score": score, "prior": round(p, 4)}))
    return matches


def _de_tiebreak(candidate: dict) -> int:
    return sum(DE_FILTER_PRIORITY.get(k, 0) for k in candidate.get("score_breakdown", {}))


def _sort_candidates(
    candidates: list[dict],
    sort: CandidateSort,
    target: CandidateTarget = "loto",
) -> list[dict]:
    if sort == "score":
        if target == "de":
            return sorted(
                candidates,
                key=lambda c: (-c["score"], -_de_tiebreak(c), c["loto"]),
            )
        return sorted(candidates, key=lambda c: (-c["score"], c["loto"]))
    if sort == "filters":
        return sorted(candidates, key=lambda c: (-c["filters_matched"], -c["score"], c["loto"]))
    return sorted(candidates, key=lambda c: c["loto"])


def _build_from_filters(
    filter_defs: list[dict],
    min_filters: int,
    sort: CandidateSort,
    top: int,
    include_reasons: bool,
    include_pair_detail: bool,
    target: CandidateTarget = "loto",
) -> tuple[list[dict], list[dict], dict[str, dict]]:
    loto_filters: dict[str, dict[str, dict]] = defaultdict(dict)
    filters_applied = []

    for filter_def in filter_defs:
        filter_key = filter_def["key"]
        matched = filter_def["fn"]()
        per_filter: dict[str, FilterMatch] = {}
        for lot, reason, detail in matched:
            if lot not in per_filter:
                per_filter[lot] = (lot, reason, detail)

        filter_matches = list(per_filter.values())
        filters_applied.append(
            {
                "name": filter_key,
                **{k: v for k, v in filter_def.items() if k not in ("key", "fn")},
                "matched": len(filter_matches),
            }
        )
        for lot, reason, detail in filter_matches:
            contribution = round(_score_contribution(filter_key, detail or {}), 2)
            loto_filters[lot][filter_key] = {
                "reason": reason,
                "score_contribution": contribution,
                "detail": detail,
            }

    candidates = []
    for lot, filters in loto_filters.items():
        if len(filters) < min_filters:
            continue
        breakdown = {k: v["score_contribution"] for k, v in filters.items()}
        entry = {
            "loto": lot,
            "score": _compute_score(breakdown),
            "filters_matched": len(filters),
            "score_breakdown": breakdown,
        }
        if include_reasons:
            entry["reasons"] = [filters[k]["reason"] for k in sorted(filters.keys())]
        if include_pair_detail:
            entry["filter_details"] = {k: filters[k]["detail"] for k in filters}
        candidates.append(entry)

    candidates = _sort_candidates(candidates, sort, target)[:top]
    return candidates, filters_applied, loto_filters


def _loto_filter_defs(
    yesterday_lotos: set[str],
    yesterday_de: str,
    weekday: int,
    as_of_date: str,
    target_date: str,
) -> list[dict]:
    return [
        {"key": "lag-1", "min_lift": 1.10, "fn": lambda: _lag1_matches(yesterday_lotos)},
        {"key": "same-day", "min_lift": 1.10, "fn": lambda: _same_day_matches(yesterday_lotos)},
        {"key": "max-cycle", "min_pct": MAX_CYCLE_MIN_PCT, "fn": lambda: _max_cycle_matches()},
        {"key": "gap-hot", "min_gap": GAP_HOT_MIN_GAP, "fn": lambda: _gap_hot_matches()},
        {
            "key": "cycle-history",
            "min_ratio": CYCLE_HISTORY_MIN_RATIO,
            "fn": lambda: _cycle_history_matches(as_of_date),
        },
        {"key": "frequency-hot", "min_lift": FREQUENCY_HOT_MIN_LIFT, "fn": lambda: _frequency_hot_matches()},
        {"key": "frequency-rank", "top_n": FREQ_RANK_TOP_N, "fn": lambda: _frequency_rank_matches()},
        {"key": "frequency-trend", "min_momentum": FREQ_TREND_MIN_MOMENTUM, "fn": lambda: _frequency_trend_matches()},
        {"key": "calendar", "min_lift": 1.05, "fn": lambda: _calendar_matches(weekday)},
        {"key": "lo-roi", "min_lift": 1.05, "window": 3, "fn": lambda: _lo_roi_matches(yesterday_de)},
        {
            "key": "cond-freq-loto",
            "min_lift": COND_FREQ_LOTO_MIN_LIFT,
            "min_occ": COND_FREQ_LOTO_MIN_OCC,
            "fn": lambda: _cond_freq_loto_matches(yesterday_de),
        },
        {
            "key": "same-date",
            "min_occ": 1,
            "fn": lambda: _same_date_matches(target_date),
        },
        {"key": "rbk-cau", "limit": 5, "lon": 1, "fn": lambda: _rbk_cau_filter_matches(as_of_date)},
        {"key": "rbk-cau-no-loan", "limit": 5, "lon": 0, "fn": lambda: _rbk_cau_no_loan_filter_matches(as_of_date)},
        {
            "key": "chi-square",
            "top_n": PREDICTION_MODEL_TOP_N,
            "fn": lambda: _chi_square_matches(as_of_date, target_date, TARGET_LOTO),
        },
        {
            "key": "bayesian-update",
            "top_n": PREDICTION_MODEL_TOP_N,
            "fn": lambda: _bayesian_update_matches(as_of_date, target_date, TARGET_LOTO),
        },
        # Cycle boost: cham trùng + số đảo từ đề hôm qua
        {
            "key": "cycle-boost",
            "fn": lambda: _cycle_boost_matches(yesterday_de),
        },
    ]


def _de_filter_defs(
    yesterday_lotos: set[str],
    yesterday_de: str,
    weekday: int,
    target_date: str,
    as_of_date: str,
) -> list[dict]:
    return [
        {
            "key": "de-intersection",
            "fn": lambda: _de_intersection_filter_matches(target_date),
        },
        {
            "key": "de-cf",
            "min_lift": 3.0,
            "fn": lambda: _de_cf_filter_matches(yesterday_de, weekday),
        },
        {"key": "de-lag1", "min_lift": 1.05, "fn": lambda: _de_lag1_filter_matches(yesterday_de)},
        {
            "key": "de-cond-prev",
            "fn": lambda: _de_cond_prev_matches(yesterday_de),
        },
        {
            "key": "cond-freq-de",
            "min_lift": COND_FREQ_DE_MIN_LIFT,
            "min_occ": COND_FREQ_DE_MIN_OCC,
            "fn": lambda: _cond_freq_de_matches(yesterday_de),
        },
        {"key": "de-calendar", "min_lift": 1.05, "fn": lambda: _de_calendar_filter_matches(weekday)},
        {
            "key": "de-loto-boost",
            "min_lift": 1.05,
            "fn": lambda: _de_loto_boost_filter_matches(yesterday_lotos),
        },
        {
            "key": "de-frequency-trend",
            "min_momentum": DE_FREQ_TREND_MIN_MOMENTUM,
            "fn": lambda: _de_frequency_trend_matches(),
        },
        {
            "key": "de-frequency-rank",
            "top_n": DE_FREQ_RANK_TOP_N,
            "fn": lambda: _de_frequency_rank_matches(),
        },
        {
            "key": "de-digit-trend",
            "min_momentum": DE_DIGIT_TREND_MIN_MOMENTUM,
            "fn": lambda: _de_digit_trend_matches(),
        },
        {
            "key": "de-chi-square",
            "top_n": PREDICTION_MODEL_TOP_N,
            "fn": lambda: _chi_square_matches(as_of_date, target_date, TARGET_DE),
        },
        {
            "key": "de-bayesian-update",
            "top_n": PREDICTION_MODEL_TOP_N,
            "fn": lambda: _bayesian_update_matches(as_of_date, target_date, TARGET_DE),
        },
        {"key": "rbk-cau", "limit": 5, "lon": 1, "fn": lambda: _rbk_cau_filter_matches(as_of_date)},
        {"key": "rbk-cau-no-loan", "limit": 5, "lon": 0, "fn": lambda: _rbk_cau_no_loan_filter_matches(as_of_date)},
    ]


def build_candidates(
    target_date: Optional[str] = None,
    top: Optional[int] = None,
    min_filters: int = 1,
    sort: CandidateSort = "score",
    target: CandidateTarget = "loto",
    include_reasons: bool = True,
    include_pair_detail: bool = False,
) -> dict:
    top = top if top is not None else DEFAULT_TOP[target]
    min_filters_warning: Optional[str] = None
    if target == "de" and min_filters > DE_MAX_MIN_FILTERS:
        min_filters_warning = (
            f"min_filters={min_filters} quá chặt cho đề — khuyến nghị ≤{DE_MAX_MIN_FILTERS}"
        )
    start_ms = time.perf_counter()
    target_str, as_of_str = _resolve_dates(target_date)
    target_dt = date.fromisoformat(target_str)

    ctx = get_day_context(as_of_str)
    if not ctx:
        raise ValueError(f"No draw data for as_of_date {as_of_str}")

    yesterday_lotos = ctx["loto_set"]
    yesterday_de = ctx["de"]
    weekday = target_dt.weekday()

    if target == "loto":
        filter_defs = _loto_filter_defs(yesterday_lotos, yesterday_de, weekday, as_of_str, target_str)
    else:
        filter_defs = _de_filter_defs(yesterday_lotos, yesterday_de, weekday, target_str, as_of_str)

    candidates, filters_applied, value_filters = _build_from_filters(
        filter_defs,
        min_filters,
        sort,
        top,
        include_reasons,
        include_pair_detail,
        target,
    )

    avg_filters = (
        round(sum(c["filters_matched"] for c in candidates) / len(candidates), 1)
        if candidates
        else 0.0
    )
    avg_score = round(sum(c["score"] for c in candidates) / len(candidates), 2) if candidates else 0.0
    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
    if elapsed_ms > 1000:
        logger.warning(
            "candidates query slow: %dms target=%s target_date=%s",
            elapsed_ms,
            target,
            target_str,
        )

    context = {
        "yesterday_lotos": len(yesterday_lotos),
        "yesterday_de": yesterday_de,
        "target_weekday": WEEKDAYS_VI[weekday],
    }
    if target == "loto":
        context["frequency_rank"] = get_loto_frequency_summary(limit=10)
        trend = get_loto_frequency_trend(limit=10)
        context["frequency_trend"] = {
            "trending_up": trend["trending_up"],
            "trending_down": trend["trending_down"],
            "stable_hot": trend["stable_hot"],
            "meta": trend["meta"],
        }
    else:
        context["frequency_rank"] = get_de_frequency_summary(limit=10)
        de_trend = get_de_frequency_trend(limit=10)
        context["frequency_trend"] = {
            "trending_up": de_trend["trending_up"],
            "trending_down": de_trend["trending_down"],
            "stable_hot": de_trend["stable_hot"],
            "meta": de_trend["meta"],
        }
        context["digit_trend"] = get_de_digit_trend(limit=5)

    meta = {
        "total_candidates": len(candidates),
        "target": target,
        "filters_run": len(filter_defs),
        "avg_filters_per_candidate": avg_filters,
        "avg_score": avg_score,
        "scoring_method": "lift-weighted",
        "sort": sort,
        "query_time_ms": elapsed_ms,
    }
    if target == "loto":
        meta["total_lotos_scanned"] = len(value_filters)
    else:
        meta["total_de_scanned"] = len(value_filters)
        meta["warning"] = DE_TARGET_WARNING
        from app.services.intersection_service import build_intersection

        ix = build_intersection(target_date=target_str)
        meta["intersection"] = {
            "intersection": ix["intersection"],
            "final_picks": ix["final_picks"],
            "strategy_used": ix["meta"]["strategy_used"],
        }
    if min_filters_warning:
        meta["min_filters_warning"] = min_filters_warning

    return {
        "endpoint": "candidates",
        "target": target,
        "target_date": target_str,
        "as_of_date": as_of_str,
        "disclaimer": CANDIDATES_DISCLAIMER,
        "context": context,
        "candidates": candidates,
        "filters_applied": filters_applied,
        "meta": meta,
    }


def _evaluate_loto_day(candidate_lotos: list[str], actual: set[str]) -> tuple[float, float]:
    pred = set(candidate_lotos)
    overlap = len(pred & actual)
    hit = 1.0 if overlap > 0 else 0.0
    recall = overlap / len(actual) if actual else 0.0
    return hit, recall


def _evaluate_single_day(candidates: list[str], actual: set[str]) -> tuple[float, float]:
    hit = 1.0 if set(candidates) & actual else 0.0
    return hit, hit


def _random_baseline_loto(top_k: int, trials: int = 5000) -> tuple[float, float]:
    hit_sum = 0.0
    recall_sum = 0.0
    for _ in range(trials):
        picked = {f"{v:02d}" for v in random.sample(range(100), top_k)}
        actual = {f"{v:02d}" for v in random.sample(range(100), 27)}
        hit, recall = _evaluate_loto_day(list(picked), actual)
        hit_sum += hit
        recall_sum += recall
    return hit_sum / trials, recall_sum / trials


def _random_baseline_single(top_k: int, universe: int) -> tuple[float, float]:
    rate = min(top_k, universe) / universe
    return rate, rate


def _backtest_config(
    target: CandidateTarget,
    target_dates: list[date],
    top: int,
    min_filters: int,
    sort: CandidateSort,
) -> dict:
    hit_sum = 0.0
    recall_sum = 0.0
    evaluated = 0
    for target_dt in target_dates:
        if previous_draw_date(target_dt) is None:
            continue
        try:
            result = build_candidates(
                target_date=target_dt.isoformat(),
                top=top,
                min_filters=min_filters,
                sort=sort,
                target=target,
                include_reasons=False,
            )
        except ValueError:
            continue

        if target == "de":
            candidates = [c["loto"] for c in result["candidates"]]
            actual = actual_values_for_date(target_dt, TARGET_DE)
            evaluate = _evaluate_single_day
        else:
            candidates = [c["loto"] for c in result["candidates"]]
            actual = actual_values_for_date(target_dt, TARGET_LOTO)
            evaluate = _evaluate_loto_day

        if not candidates or not actual:
            continue
        hit, recall = evaluate(candidates, actual)
        hit_sum += hit
        recall_sum += recall
        evaluated += 1
    return {
        "days_evaluated": evaluated,
        "hit_rate": hit_sum / evaluated if evaluated else 0.0,
        "recall": recall_sum / evaluated if evaluated else 0.0,
    }


def run_candidates_backtest(
    days: int = 90,
    top: Optional[int] = None,
    min_filters: int = 1,
    target: CandidateTarget = "loto",
) -> dict:
    top = top if top is not None else DEFAULT_TOP[target]
    start_ms = time.perf_counter()
    rows = fetch_all(
        """
        SELECT draw_date::text AS d FROM draws
        WHERE region = 'MB' ORDER BY draw_date DESC LIMIT %s
        """,
        (days,),
    )
    target_dates = [date.fromisoformat(r["d"]) for r in reversed(rows)]

    if target == "loto":
        rand_hit, rand_recall = _random_baseline_loto(top)
        primary_metric = "recall"
        rand_primary = rand_recall
    else:
        rand_hit, rand_recall = _random_baseline_single(top, 100)
        primary_metric = "hit_rate"
        rand_primary = rand_hit

    results = []
    if target == "de":
        configs = sorted(mf for mf in {min_filters, 1, 2} if mf <= DE_MAX_MIN_FILTERS)
    else:
        configs = sorted({min_filters, 1, 2, 3})
    for mf in configs:
        sort_mode: CandidateSort = "score" if mf == 1 else "filters"
        stats = _backtest_config(target, target_dates, top, mf, sort_mode)
        if primary_metric == "recall":
            lift = stats["recall"] / rand_primary if rand_primary > 0 else 0.0
        else:
            lift = stats["hit_rate"] / rand_primary if rand_primary > 0 else 0.0
        results.append(
            {
                "model": f"candidates (min_filters={mf}, sort={sort_mode})",
                f"hit_rate@{top}": round(stats["hit_rate"], 3),
                f"recall@{top}": round(stats["recall"], 3),
                "lift": round(lift, 2),
                "primary_metric": primary_metric,
                "days_evaluated": stats["days_evaluated"],
            }
        )

    results.append(
        {
            "model": "random_baseline",
            f"hit_rate@{top}": round(rand_hit, 3),
            f"recall@{top}": round(rand_recall, 3),
            "lift": 1.0,
            "primary_metric": primary_metric,
        }
    )

    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
    warnings: list[str] = []
    target_enabled = True
    if target == "de":
        best_lift = max(
            (r["lift"] for r in results if r["model"] != "random_baseline"),
            default=0.0,
        )
        if best_lift < 1.0:
            target_enabled = False
            warnings.append(
                "de target disabled: backtest lift < 1.0 — kết quả dưới random baseline"
            )

    response = {
        "module": "candidates",
        "type": "backtest",
        "target": target,
        "disclaimer": CANDIDATES_DISCLAIMER,
        "params": {"days": days, "top": top, "min_filters": min_filters, "target": target},
        "results": results,
        "meta": {
            "query_time_ms": elapsed_ms,
            "date_range": [target_dates[0].isoformat(), target_dates[-1].isoformat()] if target_dates else [],
            "target_enabled": target_enabled,
            "primary_metric": primary_metric,
            "days": days,
        },
    }
    if warnings:
        response["warnings"] = warnings
    return response


def evaluate_candidates(
    target_date: str,
    target: CandidateTarget = "loto",
    top: Optional[int] = None,
    min_filters: int = 1,
    sort: CandidateSort = "score",
) -> dict:
    start_ms = time.perf_counter()
    target_dt = date.fromisoformat(target_date)

    if target == "loto":
        actual = actual_values_for_date(target_dt, TARGET_LOTO)
    else:
        actual = actual_values_for_date(target_dt, TARGET_DE)
    if not actual:
        raise ValueError(f"No draw data for target_date {target_date}")

    prediction = build_candidates(
        target_date=target_date,
        top=top,
        min_filters=min_filters,
        sort=sort,
        target=target,
        include_reasons=False,
    )
    preds = [c["loto"] for c in prediction["candidates"]]

    actual_payload: dict = {}
    if target == "de":
        de_val = next(iter(actual))
        actual_payload["de"] = de_val
        hit = de_val in preds
        metrics = {
            "primary_metric": "hit_rate",
            "hit": hit,
            "actual_de": de_val,
            "rank": preds.index(de_val) + 1 if hit else None,
            "top_k": len(preds),
        }
    else:
        actual_payload["loto"] = sorted(actual)
        hits = sorted(set(preds) & actual)
        metrics = {
            "primary_metric": "recall",
            "hit_day": bool(hits),
            "hits": hits,
            "hits_count": len(hits),
            "top_k": len(preds),
            "recall": round(len(hits) / len(actual), 3) if actual else 0.0,
        }

    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
    return {
        "endpoint": "candidates/evaluate",
        "target": target,
        "target_date": target_date,
        "as_of_date": prediction["as_of_date"],
        "disclaimer": CANDIDATES_DISCLAIMER,
        "prediction": preds,
        "actual": actual_payload,
        "metrics": metrics,
        "meta": {"query_time_ms": elapsed_ms},
    }


def persist_candidate_snapshot(result: dict, min_filters: int = 1, top: Optional[int] = None) -> int:
    top = top if top is not None else len(result.get("candidates", []))
    payload = {
        "target_date": result["target_date"],
        "as_of_date": result["as_of_date"],
        "target": result["target"],
        "top": top,
        "min_filters": min_filters,
        "sort": result["meta"]["sort"],
    }
    full = {**result, **payload}
    return candidate_repo.save_snapshot(full)


def persist_daily_candidates() -> list[int]:
    latest = latest_draw_date()
    if latest is None:
        logger.warning("persist_daily_candidates: no draw data")
        return []

    next_day = (latest + timedelta(days=1)).isoformat()
    ids: list[int] = []
    for target in (TARGET_LOTO, TARGET_DE):
        try:
            result = build_candidates(target_date=next_day, target=target)
            ids.append(persist_candidate_snapshot(result, min_filters=1))
        except ValueError as exc:
            logger.warning("persist_daily_candidates failed target=%s: %s", target, exc)
    return ids


def get_candidate_history(
    limit: int = 30,
    target: Optional[CandidateTarget] = None,
    target_date: Optional[str] = None,
) -> dict:
    rows = candidate_repo.list_snapshots(limit=limit, target=target, target_date=target_date)
    return {
        "endpoint": "candidates/history",
        "count": len(rows),
        "snapshots": rows,
    }


def get_candidate_snapshot(
    target_date: str,
    target: CandidateTarget,
    top: Optional[int] = None,
    min_filters: int = 1,
    sort: CandidateSort = "score",
) -> dict:
    top = top if top is not None else DEFAULT_TOP[target]
    row = candidate_repo.get_snapshot(target_date, target, top, min_filters, sort)
    if not row:
        raise ValueError(f"No snapshot for {target_date} target={target}")
    return row
