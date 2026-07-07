from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.repositories.forum_repo import forum_repo
from app.services.expert_scorer import (
    DEFAULT_SCORING_MODE,
    SCORING_MODES,
    dedupe_picks_by_user,
    expert_effective_weight,
    expert_performance,
    expert_weight,
    live_experts,
)
from app.services.expert_winrate_service import DEFAULT_PERIOD_LABEL, period_display_label

SCORING_MODE_LABELS = {
    "blend": "Effective (blend)",
    "weight": "W thủ công",
    "measured": "Hiệu suất đo được",
}

DAN_PICK_TYPES = frozenset({"dan_de", "dan_40s", "dan_36s", "dan_64s"})
DAN_SIZE_LABELS = {"dan_40s": "40s", "dan_36s": "36s", "dan_64s": "64s", "dan_de": "dàn"}


@dataclass(frozen=True)
class ScoringContext:
    mode: str
    period_label: str

    def scoring_w(self, user: str, pick_type: str) -> float:
        if self.mode == "weight":
            return expert_weight(user, pick_type)
        return expert_effective_weight(
            user, pick_type, mode=self.mode, period_label=self.period_label,
        )

    def effective_w(self, user: str, pick_type: str) -> float:
        return expert_effective_weight(
            user, pick_type, mode=self.mode, period_label=self.period_label,
        )

    def perf_w(self, user: str, pick_type: str) -> float:
        """
        Performance-first weight (independent of manual W).

        Uses measured mode so that experts with higher observed hit-rate (with
        Wilson + sample ramp) are prioritized even if manual weights are low.
        """
        return expert_effective_weight(
            user, pick_type, mode="measured", period_label=self.period_label,
        )


def resolve_scoring_context(
    scoring_mode: str | None = None,
    performance_period: str | None = None,
) -> ScoringContext:
    mode = (scoring_mode or DEFAULT_SCORING_MODE).strip().lower()
    if mode not in SCORING_MODES:
        raise ValueError(f"Invalid scoring_mode: {mode!r}; use weight|measured|blend")
    period = performance_period or DEFAULT_PERIOD_LABEL
    return ScoringContext(mode=mode, period_label=period)


def _infer_dan_pick_type_from_row(pick: dict) -> str:
    pt = pick.get("pick_type", "dan_de")
    if pt in DAN_PICK_TYPES and pt != "dan_de":
        return pt
    nums = pick.get("numbers") or []
    raw = pick.get("raw_excerpt") or ""
    thread = pick.get("forum") or ""
    count = len(nums)
    blob = f"{thread} {raw}".lower()
    if "64s" in blob or count >= 58:
        return "dan_64s"
    if "36s" in blob:
        return "dan_36s"
    if "40s" in blob or count >= 38:
        return "dan_40s"
    if count >= 30:
        return "dan_36s"
    return "dan_de"


def _collect_dan_board(picks: list[dict], ctx: ScoringContext) -> list[dict]:
    rows: list[dict] = []
    for p in picks:
        pt = p.get("pick_type", "")
        if pt not in DAN_PICK_TYPES:
            continue
        nums = list(p.get("numbers") or [])
        if len(nums) < 20:
            continue
        resolved = _infer_dan_pick_type_from_row(p)
        w = expert_weight(p["username"], resolved)
        eff = ctx.effective_w(p["username"], resolved)
        perf = expert_performance(p["username"], resolved, ctx.period_label)
        rows.append({
            "user": p["username"],
            "pick_type": resolved,
            "size": DAN_SIZE_LABELS.get(resolved, "dàn"),
            "count": len(nums),
            "weight": round(w, 3),
            "effective_weight": eff,
            "performance": perf,
            "numbers": nums,
            "posted_at": p.get("posted_at"),
            "forum": p.get("forum"),
        })
    if ctx.mode == "weight":
        rows.sort(key=lambda x: (-x["weight"], x["size"], x["user"]))
    else:
        rows.sort(key=lambda x: (-x["effective_weight"], x["size"], x["user"]))
    return rows


def _live_experts_no_dan(picks: list[dict], ctx: ScoringContext) -> list[dict]:
    filtered = [p for p in picks if p.get("pick_type") not in DAN_PICK_TYPES]
    return live_experts(
        filtered, scoring_mode=ctx.mode, period_label=ctx.period_label,
    )


def _collect_de_by_expert(
    picks: list[dict], dan_board: list[dict], ctx: ScoringContext,
) -> list[dict]:
    """Tóm tắt chốt đề theo từng cao thủ — dàn + chạm/đầu/tổng."""
    users: dict[str, dict] = {}

    def ensure(user: str) -> dict:
        if user not in users:
            w = expert_weight(user, "dan_de")
            users[user] = {
                "user": user,
                "dan_size": None,
                "dan_count": 0,
                "dan_preview": [],
                "de_cham": [],
                "de_dau": [],
                "de_tong": [],
                "btd": [],
                "btd_dau": [],
                "forum": None,
                "weight": round(w, 3),
                "effective_weight": ctx.effective_w(user, "dan_de"),
                "performance": expert_performance(user, "dan_de", ctx.period_label),
            }
        return users[user]

    for row in dan_board:
        u = row["user"]
        entry = ensure(u)
        nums = [_norm_loto(n) for n in row.get("numbers") or []]
        entry["dan_size"] = row["size"]
        entry["dan_count"] = row["count"]
        entry["dan_preview"] = nums[:15]
        entry["weight"] = row.get("weight") or entry["weight"]
        entry["effective_weight"] = row.get("effective_weight") or entry["effective_weight"]
        entry["performance"] = row.get("performance") or entry["performance"]
        if row.get("forum"):
            entry["forum"] = row["forum"]

    for p in dedupe_picks_by_user(picks):
        pt = p.get("pick_type", "")
        if pt not in ("de_cham", "de_dau", "de_tong", "btd", "btd_dau"):
            continue
        u = p["username"]
        nums = [str(n) for n in (p.get("numbers") or [])]
        entry = ensure(u)
        if p.get("forum"):
            entry["forum"] = p["forum"]
        if pt == "de_cham":
            entry["de_cham"] = nums
        elif pt == "de_dau":
            entry["de_dau"] = nums
        elif pt == "de_tong":
            entry["de_tong"] = nums
        elif pt == "btd":
            entry["btd"] = [_norm_loto(n) for n in nums]
        elif pt == "btd_dau":
            entry["btd_dau"] = nums
        entry["weight"] = round(expert_weight(u, pt), 3)
        entry["effective_weight"] = ctx.effective_w(u, pt)
        perf = expert_performance(u, pt, ctx.period_label)
        if perf:
            entry["performance"] = perf

    rows = [
        r for r in users.values()
        if r["dan_count"] or r["de_cham"] or r["de_dau"] or r["de_tong"] or r["btd"] or r["btd_dau"]
    ]
    if ctx.mode == "weight":
        rows.sort(key=lambda x: (-x["weight"], -(x["dan_count"] or 0), x["user"]))
    else:
        rows.sort(key=lambda x: (-x["effective_weight"], -(x["dan_count"] or 0), x["user"]))
    return rows


def _pick_xien_2(ranked_loto: list[dict]) -> list[str]:
    nums: list[str] = []
    seen: set = set()
    for h in ranked_loto[:6]:
        loto = h["loto"]
        if loto not in seen:
            seen.add(loto)
            nums.append(loto)
    pairs = []
    if len(nums) >= 2:
        pairs.append(f"{nums[0]}-{nums[1]}")
    if len(nums) >= 4:
        pairs.append(f"{nums[2]}-{nums[3]}")
    if len(nums) >= 6:
        pairs.append(f"{nums[4]}-{nums[5]}")
    return pairs


LOTO_PICK_TYPES = ("stl", "btl", "muc_lo")


def _norm_loto(num: str) -> str:
    return str(num).zfill(2) if len(str(num)) <= 2 else str(num)


def _aggregate_loto_scores(picks: list[dict], ctx: ScoringContext) -> list[dict]:
    scores: dict[str, dict] = {}
    for p in dedupe_picks_by_user(picks):
        pt = p.get("pick_type", "")
        if pt not in LOTO_PICK_TYPES:
            continue
        user = p["username"]
        w = ctx.scoring_w(user, pt)
        for num in p.get("numbers") or []:
            n = _norm_loto(num)
            if n not in scores:
                scores[n] = {"loto": n, "score": 0.0, "users": [], "types": []}
            scores[n]["score"] += w
            if user not in scores[n]["users"]:
                scores[n]["users"].append(user)
            if pt not in scores[n]["types"]:
                scores[n]["types"].append(pt)
    rows = list(scores.values())
    for r in rows:
        r["users"] = list(dict.fromkeys(r["users"]))
        r["types"] = list(dict.fromkeys(r["types"]))
        r["reasons"] = [f"{', '.join(r['users'])} ({', '.join(r['types'])})"]
    rows.sort(key=lambda x: (-x["score"], x["loto"]))
    return rows


def _aggregate_loto_consensus(picks: list[dict], ctx: ScoringContext) -> list[dict]:
    """Đồng thuận lô: mỗi cao thủ +1 phiếu / số. Hòa phiếu: ưu tiên số cao thủ ít trọng số."""
    scores: dict[str, dict] = {}
    for p in dedupe_picks_by_user(picks):
        pt = p.get("pick_type", "")
        if pt not in LOTO_PICK_TYPES:
            continue
        user = p["username"]
        w = ctx.scoring_w(user, pt)
        for num in p.get("numbers") or []:
            n = _norm_loto(num)
            if n not in scores:
                scores[n] = {
                    "loto": n,
                    "score": 0.0,
                    "weight_sum": 0.0,
                    "users": [],
                    "types": [],
                }
            if user not in scores[n]["users"]:
                scores[n]["users"].append(user)
                scores[n]["score"] += 1.0
                scores[n]["weight_sum"] += w
            if pt not in scores[n]["types"]:
                scores[n]["types"].append(pt)
    rows = list(scores.values())
    for r in rows:
        r["users"] = list(dict.fromkeys(r["users"]))
        r["types"] = list(dict.fromkeys(r["types"]))
        votes = int(r["score"])
        r["votes"] = votes
        r["reasons"] = [f"{votes} cao thủ ({', '.join(r['types'])})"]

    def _sort_key(row: dict) -> tuple:
        votes = int(row["score"])
        wsum = float(row.get("weight_sum") or 0)
        loto = row["loto"]
        if votes >= 2:
            return (-votes, -wsum, loto)
        # 1 phiếu: đẩy số từ cao thủ trọng số thấp lên (khác panel trọng số)
        return (-votes, wsum, loto)

    rows.sort(key=_sort_key)
    return rows


def _aggregate_loto_scores_perf_first(picks: list[dict], ctx: ScoringContext) -> list[dict]:
    """
    Panel 1 (Theo cao thủ): prioritize experts with higher measured performance.

    Score per number = sum(perf_w) over unique users; tie-break by vote count then
    by manual weight sum for stability.
    """
    scores: dict[str, dict] = {}
    for p in dedupe_picks_by_user(picks):
        pt = p.get("pick_type", "")
        if pt not in LOTO_PICK_TYPES:
            continue
        user = p["username"]
        pw = float(ctx.perf_w(user, pt))
        mw = float(expert_weight(user, pt))
        for num in p.get("numbers") or []:
            n = _norm_loto(num)
            if n not in scores:
                scores[n] = {
                    "loto": n,
                    "score": 0.0,       # perf score sum
                    "votes": 0,         # unique users
                    "manual_sum": 0.0,  # tie-break only
                    "users": [],
                    "types": [],
                }
            if user not in scores[n]["users"]:
                scores[n]["users"].append(user)
                scores[n]["votes"] += 1
                scores[n]["score"] += pw
                scores[n]["manual_sum"] += mw
            if pt not in scores[n]["types"]:
                scores[n]["types"].append(pt)
    rows = list(scores.values())
    for r in rows:
        r["users"] = list(dict.fromkeys(r["users"]))
        r["types"] = list(dict.fromkeys(r["types"]))
        r["reasons"] = [f"{int(r.get('votes') or 0)} cao thủ · perf {float(r.get('score') or 0):.2f}"]
    rows.sort(
        key=lambda r: (
            -float(r.get("score") or 0),
            -int(r.get("votes") or 0),
            -float(r.get("manual_sum") or 0),
            r["loto"],
        ),
    )
    return rows


def _aggregate_loto_consensus_perf_first(picks: list[dict], ctx: ScoringContext) -> list[dict]:
    """
    Panel 2 (Đồng thuận): prioritize numbers picked by many high-performance experts.

    Rank by perf_score sum first, then votes.
    """
    scores: dict[str, dict] = {}
    for p in dedupe_picks_by_user(picks):
        pt = p.get("pick_type", "")
        if pt not in LOTO_PICK_TYPES:
            continue
        user = p["username"]
        pw = float(ctx.perf_w(user, pt))
        for num in p.get("numbers") or []:
            n = _norm_loto(num)
            if n not in scores:
                scores[n] = {"loto": n, "score": 0.0, "votes": 0, "users": [], "types": []}
            if user not in scores[n]["users"]:
                scores[n]["users"].append(user)
                scores[n]["votes"] += 1
                scores[n]["score"] += pw
            if pt not in scores[n]["types"]:
                scores[n]["types"].append(pt)
    rows = list(scores.values())
    for r in rows:
        r["users"] = list(dict.fromkeys(r["users"]))
        r["types"] = list(dict.fromkeys(r["types"]))
        votes = int(r.get("votes") or 0)
        r["reasons"] = [f"{votes} cao thủ (perf-weighted)"]
    rows.sort(key=lambda r: (-float(r.get("score") or 0), -int(r.get("votes") or 0), r["loto"]))
    return rows


def _best_btl(picks: list[dict], ctx: ScoringContext) -> str | None:
    best_num: str | None = None
    best_w = -1.0
    for p in picks:
        if p.get("pick_type") != "btl":
            continue
        w = ctx.scoring_w(p["username"], "btl")
        for num in p.get("numbers") or []:
            n = str(num).zfill(2) if len(str(num)) <= 2 else str(num)
            if w > best_w:
                best_w = w
                best_num = n
    return best_num


def _best_btl_consensus(picks: list[dict], ctx: ScoringContext) -> str | None:
    ranked = _aggregate_loto_consensus(
        [p for p in dedupe_picks_by_user(picks) if p.get("pick_type") == "btl"],
        ctx,
    )
    btl_only = [r for r in ranked if "btl" in r.get("types", [])]
    return btl_only[0]["loto"] if btl_only else None


def _norm_de(n: str) -> str:
    s = str(n).strip()
    return s.zfill(2) if len(s) <= 2 else s


def _de_cham_leaders(picks: list[dict], forum: dict, ctx: ScoringContext) -> list[dict]:
    leaders: list[dict] = []
    for p in picks:
        if p.get("pick_type") != "de_cham":
            continue
        cham = [str(x) for x in (p.get("numbers") or [])]
        if not cham:
            continue
        w = expert_weight(p["username"], "de_cham")
        leaders.append({
            "user": p["username"],
            "cham": cham,
            "weight": round(w, 3),
            "effective_weight": ctx.effective_w(p["username"], "de_cham"),
        })
    if ctx.mode == "weight":
        leaders.sort(key=lambda x: (-x["weight"], x["user"]))
    else:
        leaders.sort(key=lambda x: (-x["effective_weight"], x["user"]))
    if leaders:
        return leaders
    return list(forum.get("de_cham_leaders") or [])


def _de_top4(
    picks: list[dict],
    forum: dict,
    dan_board: list[dict] | None,
    ctx: ScoringContext,
) -> list[str]:
    de_scores: dict[str, float] = {}
    dan_pool: set[str] = set()
    dan_users: set[tuple[str, str]] = set()  # (user, norm_num) from dan_board — prevent double counting
    user_counts: dict[str, set[str]] = {}  # number -> set of users who picked it

    def _track_user(num: str, user: str) -> None:
        if num not in user_counts:
            user_counts[num] = set()
        user_counts[num].add(user)

    for row in dan_board or []:
        if ctx.mode == "weight":
            w = row.get("weight") or expert_weight(row["user"], row.get("pick_type", "dan_de"))
        else:
            w = row.get("effective_weight") or ctx.scoring_w(
                row["user"], row.get("pick_type", "dan_de"),
            )
        for num in row.get("numbers") or []:
            n = _norm_de(num)
            dan_users.add((row["user"], n))
            dan_pool.add(n)
            _track_user(n, row["user"])
            de_scores[n] = de_scores.get(n, 0.0) + float(w)

    for p in picks:
        pt = p.get("pick_type", "")
        user = p["username"]
        if pt == "btd":
            w = ctx.scoring_w(user, "btd")
            for num in p.get("numbers") or []:
                n = _norm_de(num)
                dan_pool.add(n)
                _track_user(n, user)
                # Double‑counting check: user already had this number in dan_board
                if (user, n) in dan_users:
                    de_scores[n] = de_scores.get(n, 0.0) + w * 0.5
                else:
                    de_scores[n] = de_scores.get(n, 0.0) + w * 1.5
            continue
        if pt in DAN_PICK_TYPES:
            w = ctx.scoring_w(user, pt if pt != "dan_de" else "dan_de")
            for num in p.get("numbers") or []:
                n = _norm_de(num)
                dan_users.add((user, n))
                dan_pool.add(n)
                _track_user(n, user)
                de_scores[n] = de_scores.get(n, 0.0) + w
            continue
        # Skip de_cham — handled separately below
        if pt == "de_cham":
            continue
        # Handle remaining DE_FAMILY: de_dau, de_tong, std_de, btd_dau, btd_de
        DE_FAMILY = frozenset({"de_dau", "de_tong", "btd_dau", "std_de", "btd_de"})
        if pt in DE_FAMILY:
            w = ctx.scoring_w(user, pt)
            bonus_mult = 1.5 if pt in ("std_de", "btd_de") else 1.0
            if pt == "std_de":
                # std_de: numbers are pairs like "39-79", "14-41"
                for token in p.get("numbers") or []:
                    parts = str(token).replace(",", "-").split("-")
                    for part in parts:
                        n = _norm_de(part.strip())
                        dan_pool.add(n)
                        _track_user(n, user)
                        if (user, n) in dan_users:
                            de_scores[n] = de_scores.get(n, 0.0) + w * 0.5
                        else:
                            de_scores[n] = de_scores.get(n, 0.0) + w * bonus_mult
            else:
                for num in p.get("numbers") or []:
                    n = _norm_de(num)
                    dan_pool.add(n)
                    _track_user(n, user)
                    if (user, n) in dan_users:
                        de_scores[n] = de_scores.get(n, 0.0) + w * 0.5
                    else:
                        de_scores[n] = de_scores.get(n, 0.0) + w * bonus_mult

    for row in forum.get("dan_board") or []:
        for num in row.get("numbers") or []:
            dan_pool.add(_norm_de(num))

    cham_weight: dict[str, float] = {}
    for p in picks:
        if p.get("pick_type") != "de_cham":
            continue
        w = ctx.scoring_w(p["username"], "de_cham")
        for d in p.get("numbers") or []:
            cham_weight[str(d)] = max(cham_weight.get(str(d), 0.0), w)

    for entry in forum.get("de_cham_leaders") or []:
        w = ctx.scoring_w(entry.get("user", ""), "de_cham")
        for d in entry.get("cham") or []:
            cham_weight[str(d)] = max(cham_weight.get(str(d), 0.0), w)

    pool = list(de_scores.keys()) if de_scores else list(dan_pool)
    for n in pool:
        tail = n[-1]
        if tail in cham_weight:
            bonus = cham_weight[tail] * 0.5
            de_scores[n] = de_scores.get(n, 0.05) + bonus

    # Consensus bonus: +0.3 cho mỗi cao thủ từ người thứ 3 trở đi
    CONSENSUS_BONUS = 0.3
    for n in de_scores:
        users = len(user_counts.get(n, set()))
        if users >= 3:
            de_scores[n] += CONSENSUS_BONUS * (users - 2)

    if de_scores:
        return sorted(de_scores.keys(), key=lambda n: (-de_scores[n], n))[:4]
    return list(dan_pool)[:4]


def _de_top4_anti_consensus(
    picks: list[dict],
    forum: dict,
    dan_board: list[dict] | None,
    ctx: ScoringContext,
) -> list[str]:
    """
    Anti-consensus đề top 4:

    - Source constraint: only accept non-dàn đề picks from khu Thảo luận (thao_luan)
    - Prefer numbers picked by high-performance experts (measured win-rate via Wilson + ramp)
    - Exclude numbers picked by the crowd (within Thảo luận)
    """

    # Requirement: đề top 4 candidates must come from khu Thảo luận only.
    TL_FORUM = "thao_luan"

    # Step 1: Build consensus + exclusion scores
    all_nums = [str(i).zfill(2) for i in range(100)]
    consensus = {n: 0 for n in all_nums}        # count of users who HAVE this number
    inclusion = {n: 0.0 for n in all_nums}       # perf-weighted support of users who INCLUDE this number
    hi_perf_votes = {n: 0 for n in all_nums}     # count of high-perf users who include this number
    thao_luan_signal: set[str] = set()            # numbers picked in thao_luan forum (strong signal)
    tl_user_counts: dict[str, set[str]] = {n: set() for n in all_nums}

    # Also process picks (btd and other de types)
    for p in picks:
        pt = p.get("pick_type", "")
        user = p["username"]
        forum_kind = p.get("forum") or TL_FORUM
        if forum_kind != TL_FORUM:
            continue

        # Explicitly ignore dàn đề pick types for đề top 4.
        if pt in DAN_PICK_TYPES:
            continue

        if pt == "btd":
            # BTD: strong signal — bump consensus + track thao_luan
            raw_nums = p.get("numbers") or []
            pw = float(ctx.perf_w(user, "btd"))
            for d in raw_nums:
                n = _norm_de(d)
                if n in consensus:
                    consensus[n] += 1
                    inclusion[n] += pw
                    if pw >= 0.5:
                        hi_perf_votes[n] += 1
                    thao_luan_signal.add(n)
                    tl_user_counts[n].add(user)

        elif pt in frozenset({"de_dau", "de_tong", "btd_dau", "btd_de"}):
            # Single digits (0-9) or 2-digit numbers.
            raw_nums = p.get("numbers") or []
            pw = float(ctx.perf_w(user, pt))
            for d in raw_nums:
                n = _norm_de(d)
                if n in consensus:
                    consensus[n] += 1
                    inclusion[n] += pw
                    if pw >= 0.5:
                        hi_perf_votes[n] += 1
                    thao_luan_signal.add(n)
                    tl_user_counts[n].add(user)

        elif pt == "std_de":
            # std_de: numbers come as pairs like "39-79", "14-41"
            raw_nums = p.get("numbers") or []
            pw = float(ctx.perf_w(user, "std_de"))
            for token in raw_nums:
                parts = str(token).replace(",", "-").split("-")
                for part in parts:
                    n = _norm_de(part.strip())
                    if n in consensus:
                        consensus[n] += 1
                        inclusion[n] += pw
                        if pw >= 0.5:
                            hi_perf_votes[n] += 1
                        thao_luan_signal.add(n)
                        tl_user_counts[n].add(user)

    # Step 2: Dynamic threshold
    anti_threshold = _anti_threshold(consensus)
    tl_votes = {n: len(tl_user_counts[n]) for n in all_nums}
    crowd_votes = tl_votes
    crowd_nonzero = sorted(v for v in crowd_votes.values() if v > 0)
    crowd_threshold = 3
    if crowd_nonzero:
        crowd_threshold = max(3, crowd_nonzero[len(crowd_nonzero) // 2] + 1)

    # Step 3: Score & rank
    scores = {}

    for n in all_nums:
        if consensus[n] < 1:
            continue  # no one picks it — likely random junk

        # Filter out numbers too popular in TL/CN crowd, unless they have TL signal.
        if crowd_votes[n] >= crowd_threshold and n not in thao_luan_signal:
            continue

        if consensus[n] >= anti_threshold:
            # Exclude crowd numbers unless backed by strong high-performance support.
            if n not in thao_luan_signal and hi_perf_votes[n] < 2:
                continue  # too popular — anti-consensus rule

        anti_score = 1.0 / (1.0 + consensus[n])     # inverse of popularity
        incl_score = inclusion[n]                     # perf-weighted support

        # Prefer numbers chosen by high-performance experts, then anti-popularity.
        final_score = incl_score * 0.85 + anti_score * 0.15

        # Bonus for thao_luan signal: số được thảo luận chốt có tín hiệu mạnh hơn
        if n in thao_luan_signal:
            final_score += 0.4  # flat bonus — ưu tiên số từ khu thảo luận

        scores[n] = final_score

    if not scores:
        # Fallback: if threshold filters everything, relax it
        threshold_fallback = max(3, anti_threshold * 2)
        for n in all_nums:
            if consensus[n] < 1:
                continue
            if crowd_votes[n] >= crowd_threshold and n not in thao_luan_signal:
                continue
            if consensus[n] >= threshold_fallback:
                # Skip threshold for thao_luan signal
                if n not in thao_luan_signal and hi_perf_votes[n] < 2:
                    continue
            anti_score = 1.0 / (1.0 + consensus[n])
            incl_score = inclusion[n]
            final_score = incl_score * 0.85 + anti_score * 0.15
            if n in thao_luan_signal:
                final_score += 0.4
            scores[n] = final_score

    if not scores:
        # Last resort: pick lowest consensus numbers
        candidates = [n for n in all_nums if consensus[n] >= 1]
        candidates.sort(key=lambda n: (consensus[n], n))
        return candidates[:4]

    result = sorted(scores.keys(), key=lambda n: (-scores[n], n))[:4]
    return result


def _anti_threshold(consensus_scores: dict[str, int]) -> int:
    """Threshold = median, minimum 2, maximum 40."""
    values = sorted(consensus_scores.values())
    if not values:
        return 2
    median = values[len(values) // 2]
    return max(2, min(40, int(median)))


def _de_cham_consensus(picks: list[dict], forum: dict) -> list[dict]:
    """Chạm đề theo phiếu: mỗi chạm +1 khi cao thủ chốt."""
    votes: dict[str, list[str]] = {}
    for p in picks:
        if p.get("pick_type") != "de_cham":
            continue
        user = p["username"]
        for d in p.get("numbers") or []:
            key = str(d)
            if user not in votes.setdefault(key, []):
                votes[key].append(user)

    for entry in forum.get("de_cham_leaders") or []:
        user = entry.get("user", "")
        for d in entry.get("cham") or []:
            key = str(d)
            if user and user not in votes.setdefault(key, []):
                votes[key].append(user)

    rows = [
        {"cham": cham, "votes": len(users), "users": users}
        for cham, users in votes.items()
    ]
    rows.sort(key=lambda x: (-x["votes"], x["cham"]))
    return rows


def _consensus_stats(
    ranked_consensus: list[dict],
    expert_bao: list[str],
    consensus_bao: list[str],
) -> dict[str, Any]:
    votes = [int(r.get("votes") or r.get("score") or 0) for r in ranked_consensus]
    max_votes = max(votes) if votes else 0
    strong = sum(1 for v in votes if v >= 2)
    expert_set = set(expert_bao)
    consensus_set = set(consensus_bao)
    overlap = len(expert_set & consensus_set)
    total = len(expert_set | consensus_set) or 1
    return {
        "max_votes": max_votes,
        "strong_loto_count": strong,
        "bao_lo_overlap": overlap,
        "bao_lo_overlap_pct": round(overlap / total * 100),
        "has_strong_consensus": max_votes >= 2,
    }


def _forum_confidence(experts: list[dict], ctx: ScoringContext) -> float:
    if not experts:
        return 0.0
    if ctx.mode == "weight":
        avg_w = sum(e["weight"] for e in experts) / len(experts)
    else:
        avg_w = sum(e.get("effective_weight", e["weight"]) for e in experts) / len(experts)
    return round(min(1.0, 0.15 + len(experts) * 0.06 + avg_w * 0.25), 2)


def build_recommendations(
    target_date: str,
    *,
    scoring_mode: str | None = None,
    performance_period: str | None = None,
) -> dict[str, Any]:
    """Đề xuất chỉ từ cao thủ chốt số (không dùng engine)."""
    ctx = resolve_scoring_context(scoring_mode, performance_period)
    session = forum_repo.get_session(target_date)
    forum = forum_repo.summary_dict_from_picks(target_date)
    forum["target_date"] = target_date
    raw_picks = forum_repo.get_user_picks(target_date)

    # If Thảo luận picks look incomplete (common when extension poll/sync was partial),
    # refresh Thảo luận server-side once to ensure recommendations aren't built from stale data.
    TL_DE_TYPES = frozenset({"btd", "btd_de", "std_de", "de_dau", "de_tong", "btd_dau", "de_cham", "de_list"})
    tl_de = [
        p for p in raw_picks
        if p.get("forum") == "thao_luan" and p.get("pick_type") in TL_DE_TYPES
    ]
    if session is not None and not tl_de:
        try:
            from app.services.forum_crawl_service import (
                crawl_thread_all_pages,
                discover_daily_thread_slug,
                posts_to_session_dict,
            )
            from app.services.forum_ingest_service import ingest_collect_session

            slug = discover_daily_thread_slug(target_date, "thao_luan")
            if slug:
                raw_posts = [("thao_luan", slug, p) for p in crawl_thread_all_pages(slug)]
                refreshed = posts_to_session_dict(target_date, raw_posts)
                if refreshed.get("posts"):
                    ingest_collect_session(refreshed)
                    # Reload picks after refresh
                    raw_picks = forum_repo.get_user_picks(target_date)
        except Exception:
            # Best-effort refresh; fall back to existing DB state.
            pass

    # Enrich pick rows with thread info (topic) using forum session payload.
    # We already store post_id in forum_user_picks, and session payload stores {post_id -> thread_id}.
    post_to_thread: dict[str, dict[str, str]] = {}
    try:
        payload = (session or {}).get("payload") or {}
        posts = payload.get("posts") or {}
        for pid, post in posts.items():
            if not pid:
                continue
            tid = post.get("thread_id")
            if not tid:
                continue
            post_to_thread[str(pid)] = {
                "thread_id": str(tid),
                "thread_url": f"https://forumketqua.net/threads/{tid}",
            }
    except Exception:
        post_to_thread = {}

    for p in raw_picks:
        pid = str(p.get("post_id") or "")
        if pid and pid in post_to_thread:
            p.update(post_to_thread[pid])

    picks_rows = dedupe_picks_by_user(raw_picks)
    dan_board = _collect_dan_board(picks_rows, ctx)
    experts = _live_experts_no_dan(picks_rows, ctx)
    all_experts = live_experts(
        picks_rows, scoring_mode=ctx.mode, period_label=ctx.period_label,
    )

    # Panel 1: performance-first (expert performance dominates)
    ranked_loto = _aggregate_loto_scores_perf_first(picks_rows, ctx)

    # Panel 2: consensus, but weighted by expert performance
    ranked_consensus = _aggregate_loto_consensus_perf_first(picks_rows, ctx)
    btl_lo = _best_btl(picks_rows, ctx) or (ranked_loto[0]["loto"] if ranked_loto else None)
    btl_consensus = _best_btl_consensus(picks_rows, ctx) or (
        ranked_consensus[0]["loto"] if ranked_consensus else None
    )
    # Both panels use anti-consensus for đề top 4
    de_top = _de_top4_anti_consensus(picks_rows, forum, dan_board, ctx)
    de_consensus = _de_top4_anti_consensus(picks_rows, forum, dan_board, ctx)
    cham_leaders = _de_cham_leaders(picks_rows, forum, ctx)
    cham_consensus = _de_cham_consensus(picks_rows, forum)

    expert_bao = [h["loto"] for h in ranked_loto[:9]]
    consensus_bao = [h["loto"] for h in ranked_consensus[:9]]
    consensus_stats = _consensus_stats(ranked_consensus, expert_bao, consensus_bao)

    period_label = ctx.period_label
    return {
        "target_date": target_date,
        "source": "forum",
        "scoring_mode": ctx.mode,
        "scoring_mode_label": SCORING_MODE_LABELS.get(ctx.mode, ctx.mode),
        "scoring_period": period_label,
        "scoring_period_label": period_display_label(period_label),
        "performance_period": period_label,
        "performance_period_label": period_display_label(period_label),
        "confidence": _forum_confidence(all_experts, ctx),
        "expert_count": len(all_experts),
        "has_forum_session": session is not None,
        "picks": {
            "btl_lo": btl_lo,
            "bao_lo_9": expert_bao,
            "xien_2": _pick_xien_2(ranked_loto),
            "de_top_4": de_top,
        },
        "consensus": {
            "picks": {
                "btl_lo": btl_consensus,
                "bao_lo_9": consensus_bao,
                "xien_2": _pick_xien_2(ranked_consensus),
                "de_top_4": de_consensus,
            },
            "loto_top10": ranked_consensus[:10],
            "de_cham": cham_consensus,
            "stats": consensus_stats,
        },
        "dan_board": dan_board,
        "de_by_expert": _collect_de_by_expert(picks_rows, dan_board, ctx),
        "de_cham_leaders": cham_leaders,
        "forum_loto_top10": ranked_loto[:10],
        "live_experts": experts,
        "forum_summary": forum,
    }
