# SPEC: Fix đề xuất đề top 4

## Objectives

- [ ] Fix `_de_top4()` double counting BTD bonus
- [ ] Thêm `de_dau`, `de_tong`, `std_de`, `btd_dau` vào scoring
- [ ] Fix `_de_top4_consensus()` chuẩn hóa phiếu theo kích thước dàn

## Non-Goals

- [ ] Không sửa logic lô (btl/bao/xien) — chỉ trong scope đề
- [ ] Không sửa expert_weight / expert_scorer hệ thống
- [ ] Không đụng frontend extension (chỉ sửa backend `forum_recommendation_service.py`)

## Background

Hiện tại `_de_top4()` chỉ dùng 3 nguồn cho scoring:
1. `dan_board` (dàn 40s/36s/64s) — mỗi số +weight của cao thủ
2. `picks["btd"]` — bonus ×1.5
3. `cham_weight` từ `de_cham` — bonus 50% cho số có đuôi trùng chạm

Bỏ qua hoàn toàn `de_dau`, `de_tong`, `std_de`, `btd_dau`.

### DE_META_FAMILY (expert_pick_eval.py:8-10)
```
de_cham, de_dau, de_tong, btd, btd_dau, btd_de, std_de
```
Hiện `_de_top4()` chỉ xử lý: `btd`, `de_cham`, `DAN_PICK_TYPES`.
Bỏ qua: `de_dau`, `de_tong`, `std_de`, `btd_dau`, `btd_de`.

## Technical Approach

### Fix 1: BTD double counting

**Vấn đề:** Dòng 362-369 duyệt picks tìm `btd`, cộng `+ w * 1.5` cho mỗi số.
Trong khi đó dòng 350-360 duyệt `dan_board` cũng cộng `+ w` cho mỗi số.

Nếu cao thủ A vừa post dàn (số 89 trong dan_board, weight=1.0) vừa post BTD 89 (weight=1.0):
- dan_board: 89 +1.0
- btd: 89 +1.5
- Tổng: 2.5 → quá cao

**Fix:** Khi xử lý `btd`, check nếu số đã có trong `dan_pool` (từ dan_board của user đó), chỉ cộng phần bonus ×0.5 (không cộng cả w).

```python
# Gốc:
de_scores[n] = de_scores.get(n, 0.0) + w * 1.5

# Fix:
is_in_dan = n in dan_pool and any(...)  # số này đã có từ dan_board của user
de_scores[n] = de_scores.get(n, 0.0) + (w * 0.5 if is_in_dan else w * 1.5)
```

### Fix 2: Thêm de_dau, de_tong, std_de, btd_dau vào scoring

**Cách tính:**
- `de_dau`, `de_tong`, `btd_dau`: bonus ×1.0 (ngang dàn)
- `std_de`: bonus ×1.5 (ngang BTD) — vì STĐ cũng là đề trực tiếp
- `btd_de`: bonus ×1.5 (tương tự BTD)

Chỉ áp dụng bonus cho số chưa có từ dan_board của user đó (tránh double counting giống fix 1).

### Fix 3: Consensus chuẩn hóa phiếu theo kích thước dàn

**Vấn đề:** Dàn 64s → 64 phiếu (mỗi số 1 phiếu), dàn 40s → 40 phiếu. Dàn lớn hơn có ưu thế không công bằng.

**Fix:** Mỗi dàn đóng góp `1 / count` phiếu cho mỗi số. VD:
- Dàn 40s: mỗi số được `1/40 = 0.025` phiếu
- Dàn 64s: mỗi số được `1/64 ≈ 0.0156` phiếu
- Dàn 36s: mỗi số được `1/36 ≈ 0.0278` phiếu

Vậy tổng phiếu mỗi dàn = 1.0. Consensus vẫn ưu tiên số xuất hiện trong NHIỀU dàn khác nhau, nhưng không penalize dàn nhỏ.

`btd` vẫn bonus x1.5 (consensus: `1.0 * 1.5 = 1.5` điểm cho 1 số BTD).

## File thay đổi

Chỉ 1 file: `/Volumes/SSD_1TB/PROJECT/RBK/analysis-rbk-py/app/services/forum_recommendation_service.py`

Hàm sửa:
- `_de_top4()` (line 341-405) — fix 1 + fix 2
- `_de_top4_consensus()` (line 408-457) — fix 3

## Verification

Sau khi fix:
- [ ] `_de_top4()` không double count khi user vừa có dàn vừa có BTD cùng số
- [ ] `_de_top4()` sử dụng `de_dau`, `de_tong`, `std_de`, `btd_dau`, `btd_de` trong scoring
- [ ] `_de_top4_consensus()` chuẩn hóa phiếu: mỗi dàn = 1.0 total, không lệch theo kích thước
- [ ] `_de_top4_consensus()` vẫn bonus BTD ×1.5 để consistent với panel trọng số
- [ ] Chạy `python -m pytest tests/ -k "forum" -q` pass (kiểm tra test liên quan forum_recommendation_service)
