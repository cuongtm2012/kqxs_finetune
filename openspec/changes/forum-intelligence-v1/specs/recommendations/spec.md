# Spec Delta: Recommendations API

## ADDED Requirements

### REQ-REC-001: GET /forum/recommendations

Query: `target_date` (default `date.today()` server; extension truyền `runtime.target_date` từ cửa sổ collect)

Response SHALL be **forum-only** (`source: "forum"`). Không gọi `build_candidates` / engine.

```json
{
  "target_date": "2026-07-01",
  "source": "forum",
  "confidence": 0.42,
  "expert_count": 5,
  "has_forum_session": true,
  "picks": {
    "btl_lo": "68",
    "bao_lo_9": ["68", "86", "..."],
    "xien_2": ["68-86", "12-21"],
    "de_top_4": ["68", "86", "12", "21"]
  },
  "de_cham_leaders": [
    {"user": "gimala", "cham": ["8"], "weight": 0.85}
  ],
  "forum_loto_top10": [
    {
      "loto": "68",
      "score": 1.95,
      "users": ["T98", "LangThang1977"],
      "types": ["stl", "btl"],
      "reasons": ["T98, LangThang1977 (stl, btl)"]
    }
  ],
  "live_experts": [
    {
      "user": "T98",
      "pick_type": "stl",
      "numbers": ["68", "86"],
      "weight": 0.95,
      "posted_at": "...",
      "forum": "chan_nuoi"
    }
  ],
  "forum_summary": { "...": "..." }
}
```

**Ranking rules:**
- Lô: `score(n) = Σ expert_weight(user, pick_type)` cho pick_type ∈ `{stl, btl, muc_lo}`
- `btl_lo`: BTL pick có weight cao nhất; nếu không có BTL → lô rank #1
- `de_top_4`: weighted `dan_de` picks; fallback `forum_summary.dan_de[:4]`
- `confidence`: `min(1, 0.15 + expert_count×0.06 + avg_weight×0.25)`

**Scenario: Có cao thủ chốt STL**
- GIVEN session D có T98 STL `68,86` (weight 0.95)
- WHEN `GET /forum/recommendations?target_date=D`
- THEN `68` và `86` trong `forum_loto_top10` với `score >= 0.95`
- AND `live_experts` chứa T98

**Scenario: Không có forum picks**
- GIVEN không có rows trong `forum_user_picks` cho D
- THEN `expert_count=0`, `picks` rỗng/null, `forum_loto_top10=[]`
- AND response vẫn 200 (không fallback engine)

---

### REQ-REC-002: Hybrid tách khỏi API

Hybrid Engine+Forum SHALL chỉ dùng trong `scripts/xsmb_daily_report.py` (CLI).

API `/forum/recommendations` SHALL NOT trả `hybrid_loto_top10`, `hybrid_de_top10`, `engine_meta`.

---

### REQ-REC-003: Daily Report Integration

`xsmb_daily_report.py --source api` SHALL fetch forum từ `GET /forum/picks/{date}` thay `crawl_forum_picks.py`.

Report hybrid section dùng logic local `compute_hybrid_scores` + `build_candidates` — **không** gọi `/forum/recommendations`.

**Scenario: API có data**
- WHEN `--source api`
- THEN forum summary từ session payload AND hybrid section trong report vẫn chạy
