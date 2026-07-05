# SPEC: Anti-consensus đề — thay thế panel đồng thuận

## Objectives

- [ ] Thay thế panel "Theo đồng thuận" (số người chốt) bằng "Anti-consensus" (ít người chốt nhất)
- [ ] Score: blend giữa nghịch đảo consensus (ít người đánh) + nghịch đảo dàn (nhiều cao thủ loại)
- [ ] Threshold linh hoạt dựa vào ngày hôm trước

## Non-Goals

- [ ] Không sửa panel "Theo cao thủ" (trọng số) — giữ nguyên
- [ ] Không sửa lô (btl/bao/xien) — chỉ trong scope đề
- [ ] Không đổi response structure API (vẫn trả `consensus.picks.de_top_4`)

## Phân tích dữ liệu (20 ngày gần nhất)

### Khi có nhiều cao thủ (8-24 users)
- Mỗi số 00-99 đều có ít nhất 1 cao thủ chốt (100/100 picked)
- Consensus range: 4-30 votes
- Không số nào có ≤2 votes (vì dàn 40s cover nhiều)

### Khi có ít cao thủ (2-5 users)
- ~60-95% số được pick
- 35-90% số có ≤2 votes
- Có thể có số 0 votes (không ai đánh)

### Quyết định

1. **Filter min = 1**: số phải có ít nhất 1 cao thủ chốt (loại số "rác" không ai chơi)
2. **Exclude top threshold**: loại bỏ số thuộc top X% đông nhất — dùng `max_top_pct = 80%` (số có consensus trong top 20% đông nhất bị loại)
3. **Nghịch đảo dàn (exclusion score)**: mỗi số được điểm = tổng weight của cao thủ LOẠI số đó (không có trong dàn)

## Technical Approach

### Current state (trong `_de_top4_consensus()`)
Hiện tại: `counts[n] += dan_weight` (mỗi dàn 1.0 phiếu chia đều).

### New: `_de_top4_anti_consensus()`

**Input:** picks, dan_board, forum, ctx

**3 bước:**

#### Bước 1: Tính consensus + exclusion scores

```python
# Consensus: số cao thủ có số này trong dàn
consensus = {str(i).zfill(2): 0 for i in range(100)}
# Exclusion: tổng weight của cao thủ LOẠI số này (không trong dàn)
exclusion = {str(i).zfill(2): 0.0 for i in range(100)}

for row in dan_board:
    user = row["user"]
    nums = set(str(n).zfill(2) for n in (row.get("numbers") or []))
    w = row.get("weight") or expert_weight(user, ...)
    excluded_nums_count = 100 - len(nums)
    for n in range(100):
        num = str(n).zfill(2)
        if num in nums:
            consensus[num] += 1
        else:
            # weight chia đều cho các số bị loại
            exclusion[num] += w / excluded_nums_count if excluded_nums_count > 0 else 0
```

Lý do chia exclusion weight: 1 cao thủ loại 60 số → mỗi số bị loại nhận `w/60`. Công bằng, không penalize dàn nhỏ.

#### Bước 2: Tính dynamic threshold

```python
def _anti_consensus_threshold(current_consensus: dict, ctx) -> int:
    """Tính threshold: loại số có consensus >= median * 1.5 của ngày hôm trước."""
    # Fallback: dùng median của chính ngày này
    values = sorted(current_consensus.values())
    median = values[len(values) // 2]
    return max(int(median * 1.5), 3)  # minimum 3
```

#### Bước 3: Blend score & filter

```python
score = {}
for n in all_nums:
    if consensus[n] < 1:
        continue  # không ai chốt → bỏ
    
    # Anti-consensus: số càng ít người chốt càng tốt
    anti_score = 1.0 / (1 + consensus[n])  # range: 0.5 (1 vote) → 0.02 (50 votes)
    
    # Exclusion: số càng nhiều cao thủ loại càng tốt
    excl_score = exclusion[n]  # range: 0-~28 (tùy số user)
    
    # Blend: 40% anti-consensus + 60% exclusion
    final_score = anti_score * 0.4 + excl_score * 0.6
    
    # Loại số quá đông
    threshold = _anti_consensus_threshold(consensus, ctx)
    if consensus[n] >= threshold:
        continue
    
    score[n] = final_score

# Top 4
return sorted(score.keys(), key=lambda n: (-score[n], n))[:4]
```

### Blend ratio justification (40/60):
- Anti-consensus: signal "số ít người chơi" — trực tiếp từ nguyên lý của Jack
- Exclusion: signal "số bị cao thủ loại" — bổ sung, mạnh hơn khi có nhiều cao thủ
- 40/60 vì exclusion có range rộng hơn, discriminates better

### BTD bonus:
Nếu số được BTD (chốt đề trực tiếp), bonus +0.2 vào final score (không quá lớn, chỉ ưu tiên nhẹ).

## File thay đổi

Chỉ 1 file: `/Volumes/SSD_1TB/PROJECT/RBK/analysis-rbk-py/app/services/forum_recommendation_service.py`

- `_de_top4_consensus()` → replace bằng `_de_top4_anti_consensus()`
- `build_recommendations()`: gọi `_de_top4_anti_consensus()` thay vì `_de_top4_consensus()`
- Giữ nguyên response key `consensus.picks.de_top_4`

## Response structure (không đổi)

```python
"consensus": {
    "picks": {
        "btl_lo": ...,
        "bao_lo_9": ...,
        "xien_2": ...,
        "de_top_4": de_anti,  # ← chỉ đổi logic, key giữ nguyên
    },
    ...
}
```

## Verification

- [ ] Python syntax OK
- [ ] Ngày có 24 cao thủ: anti-consensus chọn số consensus 11-14 (thấp nhất)
- [ ] Ngày có 2 cao thủ: anti-consensus chọn số consensus 1 (thấp nhất)
- [ ] Không số nào có consensus ≥ threshold bị chọn
- [ ] Không số nào có 0 picks bị chọn
