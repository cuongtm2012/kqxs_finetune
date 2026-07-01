#!/usr/bin/env python3
"""XSMB Daily Report — chạy 16:00 hàng ngày, in top 20 lô + top 10 đề + intersection + forum picks + hybrid picks."""

from __future__ import annotations

import os
import sys
import json
import re
import subprocess
import argparse
import urllib.request
from collections import Counter

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.db import init_pool
from app.services.candidate_service import build_candidates
from app.services.intersection_service import build_intersection

WEEKDAYS_VI = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]

# === FORUM CRAWLER ===

def run_forum_crawl() -> dict:
    """Run crawl_forum_picks.py and parse its JSON output."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    crawl_script = os.path.join(script_dir, "crawl_forum_picks.py")
    
    if not os.path.exists(crawl_script):
        return {"error": "crawl_forum_picks.py not found"}
    
    try:
        result = subprocess.run(
            [sys.executable, crawl_script],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            return {"error": f"crawl failed: {result.stderr[:200]}"}
    except Exception as e:
        return {"error": str(e)}


def run_forum_from_api(target_date: str, base_url: str | None = None) -> dict:
    """Fetch forum summary from API (extension-ingested session)."""
    api = (base_url or os.environ.get("API_URL") or "http://localhost:18715").rstrip("/")
    url = f"{api}/forum/picks/{target_date}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        payload = data.get("payload") or data
        summary = payload.get("summary")
        if summary:
            return summary
        return {"error": "no summary in session payload"}
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"error": f"no forum session for {target_date}"}
        return {"error": f"API HTTP {e.code}"}
    except Exception as e:
        return {"error": str(e)}


# === HYBRID ENGINE: MIX ENGINE STATS + FORUM PICKS ===

def compile_forum_picks_set(forum: dict) -> tuple[set, dict, dict]:
    """Collect all forum picks into unified sets with user sources.
    
    Returns:
        stl_set: set of all STL picks from forum
        btl_set: set of all BTL picks from forum
        user_picks: dict {number: [list of users who picked it]}
    """
    stl_set = set()
    btl_set = set()
    user_picks = {}
    
    def add_pick(num, user, pick_type):
        if num not in user_picks:
            user_picks[num] = {"users": [], "types": []}
        user_picks[num]["users"].append(user)
        user_picks[num]["types"].append(pick_type)
    
    # STL K2N
    for user, data in forum.get("stl_k2n_users", {}).items():
        for p in data.get("stl", []):
            stl_set.add(p)
            add_pick(p, user, "stl_k2n")
    
    # BTL K3N
    for user, data in forum.get("btl_k3n_users", {}).items():
        for p in data.get("btl", []):
            btl_set.add(p)
            add_pick(p, user, "btl_k3n")
    
    # Daily event STL
    for user, data in forum.get("daily_users", {}).items():
        for p in data.get("stl", []):
            stl_set.add(p)
            add_pick(p, user, "daily_event")
    
    return stl_set, btl_set, user_picks


def compute_hybrid_scores(engine_candidates: list[dict], forum: dict) -> list[dict]:
    """Compute hybrid score for each engine candidate: engine_score + forum bonus.
    
    Bonus rules:
    - In engine top 10 AND ≥2 forum users pick it: +0.5 (SIÊU MẠNH)
    - In engine top 10 AND 1 forum user picks it: +0.3 (MẠNH)
    - In engine top 20 AND 1 forum user picks it: +0.15 (TỐT)
    - In engine top 10 with no forum: +0.0 (TỐT vốn dĩ)
    """
    _, _, user_picks = compile_forum_picks_set(forum)
    
    hybrid = []
    for rank, c in enumerate(engine_candidates, 1):
        num = c["loto"]
        engine_score = c["score"]
        matched = c.get("filters_matched", 0)
        
        bonus = 0.0
        reasons = []
        
        if num in user_picks:
            n_users = len(set(user_picks[num]["users"]))
            pick_types = list(set(user_picks[num]["types"]))
            
            if rank <= 10 and n_users >= 2:
                bonus = 0.5
                reasons.append(f"🔥 {n_users} cao thủ ({', '.join(pick_types)})")
            elif rank <= 10 and n_users >= 1:
                bonus = 0.3
                reasons.append(f"⚡ 1 cao thủ ({pick_types[0]})")
            elif n_users >= 1:
                bonus = 0.15
                reasons.append(f"👍 1 cao thủ ({pick_types[0]})")
        
        hybrid.append({
            "loto": num,
            "engine_score": engine_score,
            "filters": matched,
            "bonus": bonus,
            "hybrid_score": engine_score + bonus,
            "reasons": reasons,
        })
    
    # Sort by hybrid_score descending
    hybrid.sort(key=lambda x: x["hybrid_score"], reverse=True)
    return hybrid


def compute_sieu_manh(hybrid_scores: list[dict], num: str = None) -> list[dict]:
    """Filter numbers with bonus >= 0.5 (SIÊU MẠNH)."""
    return [h for h in hybrid_scores if h["bonus"] >= 0.5]


def compute_hybrid_de(engine_de: list[dict], forum: dict) -> list[dict]:
    """Boost đề numbers that match cao thủ chạm.
    
    Rules:
    - In top 10 engine AND matches gimala chạm: +0.4 (SIÊU MẠNH)
    - In top 10 engine AND matches other cao thủ chạm: +0.2
    """
    # Collect all cham from cao thủ
    cham_sets = {}
    for entry in forum.get("de_cham_leaders", []):
        user = entry["user"]
        unique_cham = list(dict.fromkeys(entry["cham"]))
        cham_sets[user] = set(unique_cham)
    
    hybrid_de = []
    for rank, c in enumerate(engine_de, 1):
        num = c["loto"]
        score = c["score"]
        
        bonus = 0.0
        reasons = []
        
        # Check if number ends with any cham digit
        last_digit = num[-1]
        for user, cham_set in cham_sets.items():
            if last_digit in cham_set:
                if user == "gimala":
                    bonus = 0.4
                    reasons.append(f"🔥 chạm {last_digit} (gimala)")
                else:
                    bonus = max(bonus, 0.2)
                    reasons.append(f"⚡ chạm {last_digit} ({user})")
        
        # Check if number itself is in dan_de
        dan_de = forum.get("dan_de", [])
        if num in dan_de:
            bonus += 0.15
            reasons.append("có trong dàn đề")
        
        hybrid_de.append({
            "loto": num,
            "engine_score": score,
            "bonus": min(bonus, 0.6),  # cap at 0.6
            "hybrid_score": score + bonus,
            "reasons": reasons,
        })
    
    hybrid_de.sort(key=lambda x: x["hybrid_score"], reverse=True)
    return hybrid_de


def pick_btl_lo(hybrid_loto: list[dict], forum: dict) -> str:
    """Pick BTL LÔ: ưu tiên hybrid cao nhất, sau đó engine score."""
    # Top 1 hybrid
    return hybrid_loto[0]["loto"] if hybrid_loto else "??"


def pick_xien_2(hybrid_loto: list[dict], forum: dict) -> list[str]:
    """Pick 3 XIÊN 2 pairs: mix engine top + forum picks."""
    top_hybrid = [h["loto"] for h in hybrid_loto[:6]]
    
    # Deduplicate
    seen = set()
    pairs = []
    for n in top_hybrid:
        if n not in seen:
            seen.add(n)
    
    nums = list(seen)
    pairs = []
    if len(nums) >= 2:
        pairs.append(f"{nums[0]}-{nums[1]}")
    if len(nums) >= 4:
        pairs.append(f"{nums[2]}-{nums[3]}")
    if len(nums) >= 6:
        pairs.append(f"{nums[4]}-{nums[5]}")
    
    return pairs


def pick_bao_lo(hybrid_loto: list[dict]) -> list[str]:
    """Pick 9 BAO LÔ: top hybrid scores."""
    return [h["loto"] for h in hybrid_loto[:9]]


def pick_de(hybrid_de: list[dict]) -> list[str]:
    """Pick top 4 đề."""
    return [h["loto"] for h in hybrid_de[:4]]


# === REPORT HELPERS ===

def fmt_highlights(c: dict) -> list[str]:
    highlights = []
    for reason in c.get("reasons", []):
        parts = reason.split("—")
        if len(parts) >= 2:
            highlights.append(parts[1].strip())
        else:
            highlights.append(reason)
    return highlights


def fmt_hybrid_picks(hybrid_loto: list[dict], hybrid_de: list[dict], forum: dict) -> list[str]:
    """Format hybrid picks section with tiers."""
    lines = []
    
    # Detect SIÊU MẠNH numbers
    sieu_manh = [h for h in hybrid_loto if h["bonus"] >= 0.5]
    manh = [h for h in hybrid_loto if 0.3 <= h["bonus"] < 0.5]
    tot = [h for h in hybrid_loto if 0.15 <= h["bonus"] < 0.3]
    
    lines.append("")
    lines.append("🔥 **HYBRID PICKS (Engine + Forum)**")
    lines.append("")
    
    if sieu_manh:
        lines.append("**SIÊU MẠNH:**")
        for h in sieu_manh:
            reasons = "; ".join(h["reasons"])
            lines.append(f"  🔥 **{h['loto']}** (hybrid {h['hybrid_score']:.2f} = engine {h['engine_score']:.2f} + bon {h['bonus']:.2f}) — {reasons}")
        lines.append("")
    
    if manh:
        lines.append("**MẠNH:**")
        for h in manh:
            reasons = "; ".join(h["reasons"])
            lines.append(f"  ⚡ **{h['loto']}** (hybrid {h['hybrid_score']:.2f}) — {reasons}")
        lines.append("")
    
    # BTL + XIEN + BAO LO
    bt_lo = pick_btl_lo(hybrid_loto, forum)
    xien = pick_xien_2(hybrid_loto, forum)
    bao_lo = pick_bao_lo(hybrid_loto)
    de_picks = pick_de(hybrid_de)
    
    lines.append("---")
    lines.append("")
    lines.append("🏆 **BẠCH THỦ & XIÊN**")
    lines.append("")
    lines.append(f"| Loại | Số |")
    lines.append(f"|------|-----|")
    
    # Find BTL reason
    btl_reason = ""
    for h in hybrid_loto:
        if h["loto"] == bt_lo:
            btl_reason = f" (engine {h['engine_score']:.2f}" + (f" + {h['bonus']:.2f} bon" if h['bonus'] > 0 else "") + f")"
            break
    lines.append(f"| LÔ BẠCH THỦ | **{bt_lo}**{btl_reason} |")
    lines.append(f"| XIÊN 2 | {' / '.join(xien)} |")
    lines.append(f"| ĐỀ ĐẦU – ĐUÔI | {', '.join(de_picks)} |")
    
    lines.append("")
    lines.append(f"📊 **BAO LÔ:** {', '.join(bao_lo)}")
    
    lines.append("")
    lines.append("**Top 10 Hybrid Lô:**")
    lines.append("```")
    lines.append(f"{'#':>3} {'Số':>4} {'Score':>7} {'Bon':>5} {'Hybrid':>7}  {'Lý do'}")
    lines.append("-" * 50)
    for i, h in enumerate(hybrid_loto[:10], 1):
        reason_str = "; ".join(h["reasons"]) if h["reasons"] else "engine thuần"
        lines.append(f"{i:>3}  {h['loto']:>4}  {h['engine_score']:.2f}  +{h['bonus']:.2f}  {h['hybrid_score']:.2f}  {reason_str}")
    lines.append("```")
    
    lines.append("")
    lines.append("**Top 10 Hybrid Đề:**")
    lines.append("```")
    lines.append(f"{'#':>3} {'Số':>4} {'Score':>7} {'Bon':>5} {'Hybrid':>7}  {'Lý do'}")
    lines.append("-" * 50)
    for i, h in enumerate(hybrid_de[:10], 1):
        reason_str = "; ".join(h["reasons"]) if h["reasons"] else "engine thuần"
        lines.append(f"{i:>3}  {h['loto']:>4}  {h['engine_score']:.2f}  +{h['bonus']:.2f}  {h['hybrid_score']:.2f}  {reason_str}")
    lines.append("```")
    
    return lines


def fmt_forum_section(forum: dict) -> list[str]:
    """Format forum picks section."""
    lines = []
    
    if forum.get("error"):
        lines.append(f"  ⚠️ Forum crawl: {forum['error']}")
        return lines
    
    lines.append("")
    lines.append("📋 **FORUM CAO THỦ**")
    lines.append("")
    
    stl_users = forum.get("stl_k2n_users", {})
    if stl_users:
        lines.append("**STL K2N hôm nay:**")
        for user, data in stl_users.items():
            raw = data.get("raw", "")
            latest = data.get("stl", [])
            today_match = re.findall(r'STL\s+(\d{2})\s*[,]\s*(\d{2})\s*(?:TỪ|từ)\s*27', raw)
            if today_match:
                pick = f"{today_match[-1][0]}-{today_match[-1][1]}"
                lines.append(f"  • **{user}**: {pick} ← đang nuôi hôm nay")
            elif latest:
                lines.append(f"  • **{user}**: {', '.join(latest[:2])} (số cuối)")
    
    btl_users = forum.get("btl_k3n_users", {})
    if btl_users:
        lines.append("")
        lines.append("**BTL K3N (đang nuôi):**")
        for user, data in btl_users.items():
            raw = data.get("raw", "")
            today_match = re.findall(r'BTL\s+(\d{2})\s*(?:TỪ|từ)\s*27', raw)
            if today_match:
                lines.append(f"  • **{user}**: BTL {today_match[-1]} ← đang nuôi hôm nay")
            elif data.get("btl"):
                lines.append(f"  • **{user}**: {', '.join(data['btl'][:3])}")
    
    daily = forum.get("daily_users", {})
    if daily:
        lines.append("")
        lines.append("**Event STL hôm nay:**")
        for user, data in daily.items():
            if data.get("stl"):
                lines.append(f"  • **{user}**: {'-'.join(data['stl'])}")
    
    return lines


def fmt_forum_recommendations(reco: dict) -> list[str]:
    """Format forum-only recommendations (same as extension tab Đề xuất)."""
    lines = []
    lines.append("")
    lines.append("🎯 **ĐỀ XUẤT CAO THỦ (forum-only)**")
    lines.append("")
    picks = reco.get("picks") or {}
    lines.append(f"• Cao thủ chốt: **{reco.get('expert_count', 0)}**")
    lines.append(f"• BTL lô: **{picks.get('btl_lo') or '—'}**")
    lines.append(f"• Bao lô 9: {', '.join(picks.get('bao_lo_9') or []) or '—'}")
    lines.append(f"• Xiên 2: {' / '.join(picks.get('xien_2') or []) or '—'}")
    lines.append(f"• Đề top 4: {', '.join(picks.get('de_top_4') or []) or '—'}")

    consensus = reco.get("consensus") or {}
    c_picks = consensus.get("picks") or {}
    if c_picks:
        lines.append("")
        lines.append("🤝 **ĐỒNG THUẬN (số người chốt)**")
        lines.append("")
        lines.append(f"• BTL lô: **{c_picks.get('btl_lo') or '—'}**")
        lines.append(f"• Bao lô 9: {', '.join(c_picks.get('bao_lo_9') or []) or '—'}")
        lines.append(f"• Xiên 2: {' / '.join(c_picks.get('xien_2') or []) or '—'}")
        lines.append(f"• Đề top 4: {', '.join(c_picks.get('de_top_4') or []) or '—'}")
        c_cham = consensus.get("de_cham") or []
        if c_cham:
            lines.append(
                "• Chạm đề: "
                + ", ".join(f"{c['cham']} ({c['votes']})" for c in c_cham[:6])
            )

    cham = reco.get("de_cham_leaders") or []
    if cham:
        lines.append("")
        lines.append("**Chạm đề:**")
        for c in cham[:8]:
            w = c.get("weight")
            suffix = f" (w={w})" if w is not None else ""
            lines.append(f"  • **{c['user']}**{suffix}: chạm {', '.join(c.get('cham') or [])}")

    dans = reco.get("dan_board") or []
    if dans:
        lines.append("")
        lines.append("**Dàn đề cao thủ:**")
        for d in dans:
            nums = ", ".join((d.get("numbers") or [])[:12])
            more = len(d.get("numbers") or []) - 12
            tail = f" … +{more}" if more > 0 else ""
            lines.append(
                f"  • **{d['user']}** ({d.get('size', '?')} · {d.get('count', 0)}s · w={d.get('weight', '?')}): {nums}{tail}"
            )

    top = reco.get("forum_loto_top10") or []
    if top:
        lines.append("")
        lines.append("**Top lô cao thủ:**")
        lines.append("```")
        lines.append(f"{'#':>3} {'Số':>4} {'W':>6}  Cao thủ")
        lines.append("-" * 40)
        for i, r in enumerate(top, 1):
            users = ", ".join(r.get("users") or [])[:30]
            lines.append(f"{i:>3}  {r['loto']:>4}  {r['score']:>6.2f}  {users}")
        lines.append("```")
    return lines


def run_report(source: str = "crawl", api_url: str | None = None, mode: str = "hybrid") -> str:
    init_pool(min_size=1, max_size=1)
    
    # --- Loto candidates first to get target_date ---
    loto_result = build_candidates(target="loto", top=30, min_filters=1, sort="score", include_reasons=True)
    target_date = loto_result["target_date"]

    if source == "api":
        forum_data = run_forum_from_api(target_date, api_url)
    else:
        forum_data = run_forum_crawl()
    ctx = loto_result["context"]
    yesterday_de = ctx.get("yesterday_de", "??")
    target_weekday = ctx.get("target_weekday", "??")

    lines = []
    if source == "api":
        if forum_data.get("error"):
            lines.append(f"⚠️ Forum API: {forum_data['error']}")
        else:
            lines.append(f"📡 Forum source: API ({target_date})")
    lines.append(f"🎯 XSMB — {target_weekday}, {target_date}")
    lines.append(f"📌 Đề hôm qua: **{yesterday_de}**")
    if mode == "hybrid":
        meta = loto_result.get("meta", {})
        conf = meta.get("confidence", 0)
        if conf > 0:
            bar = "█" * int(conf * 10) + "░" * (10 - int(conf * 10))
            lines.append(f"📈 Độ tin cậy engine: {conf:.0%} {bar}")
    lines.append("")
    
    if mode == "hybrid":
        lines.append("📋 **ENGINE RAW — TOP 20 LÔ**")
        lines.append("```")
        lines.append(f"{'#':>3} {'Số':>4} {'Score':>7} {'F':>3}  {'Nổi bật'}")
        lines.append("-" * 45)
        for i, c in enumerate(loto_result["candidates"][:20], 1):
            highlights = fmt_highlights(c)
            hl_str = "; ".join(highlights[:2])
            lines.append(f"{i:>3}  {c['loto']:>4}  {c['score']:.2f}  {c['filters_matched']:>3}  {hl_str}")
        lines.append("```")
        lines.append("")

        lines.append("🏆 **ENGINE RAW — TOP 10 ĐỀ**")
        de_result = None
        try:
            de_result = build_candidates(target="de", top=10, min_filters=1, sort="score", include_reasons=True)
            lines.append("```")
            lines.append(f"{'#':>3} {'Số':>4} {'Score':>7} {'F':>3}  {'Nổi bật'}")
            lines.append("-" * 45)
            for i, c in enumerate(de_result["candidates"][:10], 1):
                highlights = fmt_highlights(c)
                hl_str = "; ".join(highlights[:2])
                lines.append(f"{i:>3}  {c['loto']:>4}  {c['score']:.2f}  {c['filters_matched']:>3}  {hl_str}")
            lines.append("```")
        except Exception as e:
            lines.append(f"  ❌ Lỗi đề: {e}")

    lines.extend(fmt_forum_section(forum_data))

    if mode == "forum":
        from app.services.forum_recommendation_service import build_recommendations
        reco = build_recommendations(target_date)
        lines.extend(fmt_forum_recommendations(reco))
    else:
        de_result = de_result if mode == "hybrid" and "de_result" in locals() else None
        hybrid_loto = compute_hybrid_scores(loto_result["candidates"], forum_data)
        de_list = de_result.get("candidates", []) if de_result else []
        hybrid_de = compute_hybrid_de(de_list, forum_data)
        lines.extend(fmt_hybrid_picks(hybrid_loto, hybrid_de, forum_data))
    
    lines.append("")
    lines.append("📊 Tham khảo — KQXS dựa trên quay số ngẫu nhiên. Chúc may mắn! 🍀")
    
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="XSMB daily report")
    parser.add_argument("--source", choices=["crawl", "api"], default="crawl")
    parser.add_argument("--mode", choices=["hybrid", "forum"], default="hybrid",
                        help="hybrid=engine+forum; forum=cao thủ only (khớp extension)")
    parser.add_argument("--api-url", default=None, help="API base URL (default API_URL or :18715)")
    args = parser.parse_args()
    try:
        print(run_report(source=args.source, api_url=args.api_url, mode=args.mode))
    except Exception as e:
        import traceback
        print(f"❌ Error: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
