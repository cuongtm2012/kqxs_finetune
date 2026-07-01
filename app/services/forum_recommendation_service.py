from __future__ import annotations

from typing import Any

from app.repositories.forum_repo import forum_repo
from app.services.expert_scorer import dedupe_picks_by_user, expert_performance, expert_weight, live_experts


DAN_PICK_TYPES = frozenset({"dan_de", "dan_40s", "dan_36s", "dan_64s"})
DAN_SIZE_LABELS = {"dan_40s": "40s", "dan_36s": "36s", "dan_64s": "64s", "dan_de": "dàn"}


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


def _collect_dan_board(picks: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for p in picks:
        pt = p.get("pick_type", "")
        if pt not in DAN_PICK_TYPES:
            continue
        nums = list(p.get("numbers") or [])
        if len(nums) < 20:
            continue
        resolved = _infer_dan_pick_type_from_row(p)
        w = expert_weight(p["username"], "dan_de")
        perf = expert_performance(p["username"], "dan_de")
        rows.append({
            "user": p["username"],
            "pick_type": resolved,
            "size": DAN_SIZE_LABELS.get(resolved, "dàn"),
            "count": len(nums),
            "weight": round(w, 3),
            "performance": perf,
            "numbers": nums,
            "posted_at": p.get("posted_at"),
            "forum": p.get("forum"),
        })
    rows.sort(key=lambda x: (-x["weight"], x["size"], x["user"]))
    return rows


def _live_experts_no_dan(picks: list[dict]) -> list[dict]:
    filtered = [p for p in picks if p.get("pick_type") not in DAN_PICK_TYPES]
    return live_experts(filtered)


def _collect_de_by_expert(picks: list[dict], dan_board: list[dict]) -> list[dict]:
    """Tóm tắt chốt đề theo từng cao thủ — dàn + chạm/đầu/tổng."""
    users: dict[str, dict] = {}

    def ensure(user: str) -> dict:
        if user not in users:
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
                "weight": round(expert_weight(user, "dan_de"), 3),
                "performance": expert_performance(user, "dan_de"),
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
        perf = expert_performance(u, pt)
        if perf:
            entry["performance"] = perf

    rows = [
        r for r in users.values()
        if r["dan_count"] or r["de_cham"] or r["de_dau"] or r["de_tong"] or r["btd"] or r["btd_dau"]
    ]
    rows.sort(key=lambda x: (-x["weight"], -(x["dan_count"] or 0), x["user"]))
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


def _aggregate_loto_scores(picks: list[dict]) -> list[dict]:
    scores: dict[str, dict] = {}
    for p in dedupe_picks_by_user(picks):
        pt = p.get("pick_type", "")
        if pt not in LOTO_PICK_TYPES:
            continue
        user = p["username"]
        w = expert_weight(user, pt)
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


def _aggregate_loto_consensus(picks: list[dict]) -> list[dict]:
    """Đồng thuận lô: mỗi cao thủ +1 phiếu / số. Hòa phiếu: ưu tiên số cao thủ ít trọng số."""
    scores: dict[str, dict] = {}
    for p in dedupe_picks_by_user(picks):
        pt = p.get("pick_type", "")
        if pt not in LOTO_PICK_TYPES:
            continue
        user = p["username"]
        w = expert_weight(user, pt)
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


def _best_btl(picks: list[dict]) -> str | None:
    best_num: str | None = None
    best_w = -1.0
    for p in picks:
        if p.get("pick_type") != "btl":
            continue
        w = expert_weight(p["username"], "btl")
        for num in p.get("numbers") or []:
            n = str(num).zfill(2) if len(str(num)) <= 2 else str(num)
            if w > best_w:
                best_w = w
                best_num = n
    return best_num


def _best_btl_consensus(picks: list[dict]) -> str | None:
    ranked = _aggregate_loto_consensus(
        [p for p in dedupe_picks_by_user(picks) if p.get("pick_type") == "btl"],
    )
    btl_only = [r for r in ranked if "btl" in r.get("types", [])]
    return btl_only[0]["loto"] if btl_only else None


def _norm_de(n: str) -> str:
    s = str(n).strip()
    return s.zfill(2) if len(s) <= 2 else s


def _de_cham_leaders(picks: list[dict], forum: dict) -> list[dict]:
    leaders: list[dict] = []
    for p in picks:
        if p.get("pick_type") != "de_cham":
            continue
        cham = [str(x) for x in (p.get("numbers") or [])]
        if not cham:
            continue
        leaders.append({
            "user": p["username"],
            "cham": cham,
            "weight": round(expert_weight(p["username"], "de_cham"), 3),
        })
    leaders.sort(key=lambda x: (-x["weight"], x["user"]))
    if leaders:
        return leaders
    return list(forum.get("de_cham_leaders") or [])


def _de_top4(picks: list[dict], forum: dict, dan_board: list[dict] | None = None) -> list[str]:
    de_scores: dict[str, float] = {}
    dan_pool: set[str] = set()

    for row in dan_board or []:
        w = row.get("weight") or expert_weight(row["user"], "dan_de")
        for num in row.get("numbers") or []:
            n = _norm_de(num)
            dan_pool.add(n)
            de_scores[n] = de_scores.get(n, 0.0) + float(w)

    for p in picks:
        pt = p.get("pick_type", "")
        if pt == "btd":
            w = expert_weight(p["username"], "btd")
            for num in p.get("numbers") or []:
                n = _norm_de(num)
                dan_pool.add(n)
                de_scores[n] = de_scores.get(n, 0.0) + w * 1.5
            continue
        if pt not in DAN_PICK_TYPES:
            continue
        w = expert_weight(p["username"], "dan_de")
        for num in p.get("numbers") or []:
            n = _norm_de(num)
            dan_pool.add(n)
            de_scores[n] = de_scores.get(n, 0.0) + w

    for row in forum.get("dan_board") or []:
        for num in row.get("numbers") or []:
            dan_pool.add(_norm_de(num))

    cham_weight: dict[str, float] = {}
    for p in picks:
        if p.get("pick_type") != "de_cham":
            continue
        w = expert_weight(p["username"], "de_cham")
        for d in p.get("numbers") or []:
            cham_weight[str(d)] = max(cham_weight.get(str(d), 0.0), w)

    for entry in forum.get("de_cham_leaders") or []:
        w = expert_weight(entry.get("user", ""), "de_cham")
        for d in entry.get("cham") or []:
            cham_weight[str(d)] = max(cham_weight.get(str(d), 0.0), w)

    pool = list(de_scores.keys()) if de_scores else list(dan_pool)
    for n in pool:
        tail = n[-1]
        if tail in cham_weight:
            bonus = cham_weight[tail] * 0.5
            de_scores[n] = de_scores.get(n, 0.05) + bonus

    if de_scores:
        return sorted(de_scores.keys(), key=lambda n: (-de_scores[n], n))[:4]
    return list(dan_pool)[:4]


def _de_top4_consensus(
    picks: list[dict],
    forum: dict,
    dan_board: list[dict] | None = None,
) -> list[str]:
    """Đồng thuận đề: đếm số cao thủ có số trong dàn (mỗi nick tính 1 lần / số)."""
    user_sets: dict[str, set[str]] = {}

    def _add(user: str, num: str) -> None:
        n = _norm_de(num)
        if user not in user_sets:
            user_sets[user] = set()
        user_sets[user].add(n)

    for row in dan_board or []:
        user = row["user"]
        for num in row.get("numbers") or []:
            _add(user, num)

    for p in picks:
        pt = p.get("pick_type", "")
        if pt == "btd":
            user = p["username"]
            for num in p.get("numbers") or []:
                _add(user, num)
            continue
        if pt not in DAN_PICK_TYPES:
            continue
        user = p["username"]
        for num in p.get("numbers") or []:
            _add(user, num)

    for row in forum.get("dan_board") or []:
        user = row.get("user", "")
        for num in row.get("numbers") or []:
            if user:
                _add(user, num)

    counts: dict[str, int] = {}
    for nums in user_sets.values():
        for n in nums:
            counts[n] = counts.get(n, 0) + 1

    if counts:
        return sorted(counts.keys(), key=lambda n: (-counts[n], n))[:4]

    pool: list[str] = []
    for nums in user_sets.values():
        pool.extend(nums)
    return sorted(dict.fromkeys(pool))[:4]


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


def _forum_confidence(experts: list[dict]) -> float:
    if not experts:
        return 0.0
    avg_w = sum(e["weight"] for e in experts) / len(experts)
    return round(min(1.0, 0.15 + len(experts) * 0.06 + avg_w * 0.25), 2)


def build_recommendations(target_date: str) -> dict[str, Any]:
    """Đề xuất chỉ từ cao thủ chốt số (không dùng engine)."""
    session = forum_repo.get_session(target_date)
    forum = forum_repo.summary_dict_from_picks(target_date)
    forum["target_date"] = target_date
    picks_rows = dedupe_picks_by_user(forum_repo.get_user_picks(target_date))
    dan_board = _collect_dan_board(picks_rows)
    experts = _live_experts_no_dan(picks_rows)
    all_experts = live_experts(picks_rows)

    ranked_loto = _aggregate_loto_scores(picks_rows)
    ranked_consensus = _aggregate_loto_consensus(picks_rows)
    btl_lo = _best_btl(picks_rows) or (ranked_loto[0]["loto"] if ranked_loto else None)
    btl_consensus = _best_btl_consensus(picks_rows) or (
        ranked_consensus[0]["loto"] if ranked_consensus else None
    )
    de_top = _de_top4(picks_rows, forum, dan_board)
    de_consensus = _de_top4_consensus(picks_rows, forum, dan_board)
    cham_leaders = _de_cham_leaders(picks_rows, forum)
    cham_consensus = _de_cham_consensus(picks_rows, forum)

    expert_bao = [h["loto"] for h in ranked_loto[:9]]
    consensus_bao = [h["loto"] for h in ranked_consensus[:9]]
    consensus_stats = _consensus_stats(ranked_consensus, expert_bao, consensus_bao)

    return {
        "target_date": target_date,
        "source": "forum",
        "confidence": _forum_confidence(all_experts),
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
        "de_by_expert": _collect_de_by_expert(picks_rows, dan_board),
        "de_cham_leaders": cham_leaders,
        "forum_loto_top10": ranked_loto[:10],
        "live_experts": experts,
        "forum_summary": forum,
    }
