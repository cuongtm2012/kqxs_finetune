# Brainstorm: Đề xuất đề theo anti-consensus

**Nguyên lý (từ Jack, 27/06):**
- Chiến thắng không thuộc về số đông
- Không có ngày nào tất cả cùng trúng hoặc tất cả cùng trượt
- Số mà cao thủ top đầu loại → không về
- Số mà ai cũng chơi → không về được

## 3 luồng dữ liệu cho Đề

### Luồng 1: Cao thủ CHỐT (đang có)
Những số được cao thủ chốt — từ dàn (40s/36s/64s), BTD, chạm, đầu, tổng.
→ Đã implement trong `_de_top4()`.

### Luồng 2: Cao thủ LOẠI (chưa có)
Những số được cao thủ chủ động loại khỏi dàn của họ.
- Dàn 40s: loại ~60 số (00-99 có 40 số trong, 60 số ngoài)
- Cao thủ có dàn nhỏ (36s) → loại 64 số
- **Observation:** 1 cao thủ loại số thì chưa nói gì. NHIỀU cao thủ cùng loại 1 số → tín hiệu mạnh.

**Ý tưởng:** Nghịch đảo dàn — track những số KHÔNG nằm trong dàn của mỗi cao thủ. Số bị loại bởi nhiều cao thủ top → ưu tiên.

### Luồng 3: Consensus cần tránh (đang có, không đúng hướng)
Đồng thuận hiện tại chọn số nhiều người chơi nhất → ngược với anti-consensus.
Cần đảo ngược: chọn số ÍT người chơi nhất.

## Phân tích dữ liệu

### Đề 2 số (00-99), tổng cộng 100 số
- Dàn 40s: chiếm 40% số
- Nếu CÓ 10 cao thủ post dàn, mỗi dàn 40s → mỗi số trung bình được 4 cao thủ chốt (lý thuyết)
- Thực tế: các số "đẹp" (kép, tổng, chạm hot) thường được nhiều dàn cover → consensus cao
- Đề thường về số "giữa" — không hot, không lạnh → anti-consensus

### Backtest Jack đã làm:
- Consensus ≥80% (10 số đám đông) → 0/27 ngày trúng!
- Anti-consensus top 36: 55.6% vs random 36% (x1.54 lift)

## Các hướng tiếp cận

### Hướng A: Nghịch đảo consensus đơn thuần
**Cách tính:**
1. Với mỗi số 00-99, đếm số cao thủ CÓ số đó trong dàn
2. Chọn top 4 số có **ít phiếu nhất** (đảo ngược consensus gốc)

**Vấn đề:**
- Số ít người chơi có thể là số "rác" không ai nghĩ tới
- Cần filter: chỉ lấy số có ít nhất 1 cao thủ chốt (không phải số không ai đụng)

### Hướng B: Anti-consensus có filter (recommended)
1. Tính consensus score cho mỗi số: số cao thủ có số đó
2. **Filter:** chỉ giữ số có consensus score > 0 (có ít nhất 1 cao thủ chốt)
3. **Invert:** sort tăng dần theo consensus score
4. **Pass:** loại bỏ số có consensus score quá cao (≥80% cao thủ)
5. Lấy top 4 từ danh sách đã filter

**Bonus:** Có thể thêm trọng số — nếu số đó được cao thủ top (weight cao) chốt, được +điểm nhẹ (để không mất hết signal).

### Hướng C: Nghịch đảo dàn (loại trừ)
1. Với mỗi cao thủ, build set số họ LOẠI (= 100 - số trong dàn)
2. Score mỗi số = tổng weight của cao thủ LOẠI số đó
3. Chọn top 4 số có LOẠI score cao nhất

**Điểm mạnh:** Số bị LOẠI bởi nhiều cao thủ top đầu → tín hiệu mạnh nhất
**Điểm yếu:** Cần giả định dàn 40s = loại 60 số có chủ đích (có thể họ chỉ không thích 40 số kia hơn)

### Hướng D: Hỗn hợp (Blend)
Kết hợp panel "theo cao thủ" (trọng số) với panel anti-consensus:
- Panel trọng số: chọn số dựa trên weight cao thủ (đã có)
- Panel anti: chọn số dựa trên nghịch đảo consensus
- **Final:** giao hoặc trung bình 2 panel (số vừa có weight cao vừa ít người chơi)

## Vị trí trong extension

Hiện tại có 2 panel cho đề:
1. **Theo cao thủ** (trọng số) — `picks.de_top_4`
2. **Theo đồng thuận** (số người chốt) — `consensus.picks.de_top_4`

**Đề xuất layout mới:**
- Giữ nguyên panel "Theo cao thủ" (trọng số)
- **Đổi panel "Theo đồng thuận" thành "Anti-consensus"** (ít người chốt nhất)
- Hoặc thêm panel thứ 3 "Loại trừ" (nghịch đảo dàn)

## Câu hỏi cho Jack

1. **Filter threshold:** Số phải có ít nhất mấy cao thủ chốt thì mới được xét? 1? 2?
2. **Cao thủ loại:** Có nên dùng luồng "cao thủ loại" (nghịch đảo dàn) không, hay chỉ dùng anti-consensus thuần?
3. **Panel thay thế:** Anh muốn thay thế panel đồng thuận bằng anti-consensus, hay thêm panel mới?
4. **Blend:** Có muốn blend panel trọng số + anti-consensus thành 1 panel "lọc" không?
