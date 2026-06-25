#!/usr/bin/env python3
"""XSMB Daily Report — chạy 16:00 hàng ngày, in top 20 lô + top 10 đề + intersection."""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.db import init_pool
from app.services.candidate_service import build_candidates
from app.services.intersection_service import build_intersection

WEEKDAYS_VI = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]


def fmt_line(symbol: str, rank: int, loto: str, score: float, filters: int, highlights: list[str]) -> str:
    hl = " — ".join(highlights) if highlights else ""
    tag = "🔥" if filters >= 5 else ""
    return f"{symbol} {rank}. **{loto}** — {score:.2f}pts ({filters} filters{tag}){hl}"


def fmt_highlights(c: dict) -> list[str]:
    """Extract highlight reasons from a candidate (reasons is list of strings)."""
    highlights = []
    for reason in c.get("reasons", []):
        parts = reason.split("—")
        if len(parts) >= 2:
            highlights.append(parts[1].strip())
        else:
            highlights.append(reason)
    return highlights


def run_report() -> str:
    init_pool(min_size=1, max_size=1)

    # --- Loto candidates (top 20) ---
    loto_result = build_candidates(target="loto", top=20, min_filters=1, sort="score", include_reasons=True)
    ctx = loto_result["context"]
    yesterday_de = ctx.get("yesterday_de", "??")
    target_weekday = ctx.get("target_weekday", "??")
    target_date = loto_result["target_date"]

    lines = []
    lines.append(f"🎯 XSMB — {target_weekday}, {target_date}")
    lines.append(f"📌 Đề hôm qua: **{yesterday_de}**")
    meta = loto_result.get("meta", {})
    conf = meta.get("confidence", 0)
    if conf > 0:
        bar = "█" * int(conf * 10) + "░" * (10 - int(conf * 10))
        lines.append(f"📈 Độ tin cậy: {conf:.0%} {bar}")
    lines.append("")

    # Top 20 Lô
    lines.append("📋 **TOP 20 LÔ**")
    lines.append("```")
    lines.append(f"{'#':>3} {'Số':>4} {'Score':>7} {'F':>3}  {'Nổi bật'}")
    lines.append("-" * 45)
    for i, c in enumerate(loto_result["candidates"][:20], 1):
        highlights = fmt_highlights(c)
        hl_str = "; ".join(highlights[:2])
        lines.append(f"{i:>3}  {c['loto']:>4}  {c['score']:.2f}  {c['filters_matched']:>3}  {hl_str}")
    lines.append("```")
    lines.append("")

    # Đề candidates (top 10)
    lines.append("🏆 **TOP 10 ĐỀ**")
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

        # Intersection engine
        ix_meta = de_result["meta"].get("intersection", {})
        if ix_meta and ix_meta.get("intersection"):
            lines.append("")
            lines.append("✨ **INTERSECTION ENGINE (CF + RBK)**")
            lines.append(f"Strategy: {ix_meta['strategy_used']}")
            for p in ix_meta["final_picks"]:
                details = []
                if p.get("cf_lift"):
                    details.append(f"CF {p['cf_lift']}x")
                if p.get("rbk_cau"):
                    details.append(f"RBK {p['rbk_cau']} cầu")
                src_tag = "⚡" if p["source"] == "intersection" else ""
                lines.append(f"  {src_tag} **{p['loto']}** — {' | '.join(details)}")
    except Exception as e:
        lines.append(f"  ❌ Lỗi đề: {e}")

    lines.append("")
    lines.append("📊 Tham khảo — KQXS dựa trên quay số ngẫu nhiên.")
    return "\n".join(lines)


if __name__ == "__main__":
    try:
        print(run_report())
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)
