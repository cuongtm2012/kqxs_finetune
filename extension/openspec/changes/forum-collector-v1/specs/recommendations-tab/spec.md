# Spec Delta: Recommendations Tab (Popup)

## ADDED Requirements

### REQ-RT-001: Tab Đề xuất

Popup SHALL có tab **Đề xuất** (cùng với Thu thập, Engine, Kết quả).

Tab Đề xuất SHALL fetch `GET {api_base_url}/forum/recommendations?target_date={getTargetDate()}` khi:
- user mở tab lần đầu, hoặc
- bấm **Tải đề xuất**, hoặc
- `target_date` đổi trong khi tab đang active (`refreshUi` interval).

`target_date` = ngày quay đang collect (sau 18:30 ICT → ngày D+1).

Fetch SHALL chạy trong popup (`recommendations-api.ts`), không bắt buộc qua service worker.

**Scenario: Load thành công (API có sẵn)**
- GIVEN API healthy và đã có forum picks cho `target_date`
- WHEN user mở tab Đề xuất
- THEN render ngay từ API (không chờ poll forum xong)
- AND hiển thị dual panel trọng số + đồng thuận, bảng cao thủ, top lô

**Scenario: API offline**
- THEN hiển thị lỗi rõ: không kết nối / thiếu `/forum` / hướng dẫn `APP_PORT=18715 python run.py`

**Scenario: Fallback port**
- GIVEN `api_base_url` là `:18715` unreachable nhưng `:8081` có `/forum`
- WHEN fetch
- THEN dùng `:8081` AND lưu lại `api_base_url` mới vào settings

---

### REQ-RT-002: Load order — API trước, poll không chặn UI

Sau 18:30 ICT, nếu session local thiếu hoặc chưa có post thảo luận, popup MAY poll forum (`POLL_NOW`) rồi sync session.

Poll SHALL NOT chặn render lần đầu khi API đã có data:
1. Fetch recommendations → render ngay nếu `has_forum_session` hoặc `expert_count > 0`
2. Poll forum (timeout 45s) + sync session nếu cần
3. Re-fetch + re-render

`pushSessionToApi` lỗi SHALL NOT làm mất data đã render — chỉ bỏ qua sync.

**Scenario: Poll chậm**
- GIVEN API đã có picks
- WHEN poll timeout
- THEN vẫn hiển thị data API
- AND hint poll lỗi (nếu chưa có data local)

---

### REQ-RT-003: Forum-only UI (dual panel)

Tab Đề xuất SHALL NOT hiển thị engine score, hybrid score, hay độ tin cậy engine.

| Vùng UI | Nguồn API |
|---------|-----------|
| Panel **Theo cao thủ (trọng số)** | `picks.*` |
| Panel **Theo đồng thuận** | `consensus.picks.*`, `consensus.stats` |
| Chạm đề (cả 2 panel) | `de_cham_leaders[]`, `consensus.de_cham[]` |
| Meta | `target_date`, `expert_count` |
| Chốt đề theo cao thủ | `de_by_expert[]` |
| Dàn đề chi tiết | `dan_board[]` |
| Gợi ý loại trừ | derived từ `dan_board` + `performance` |
| Cao thủ đang chốt | `live_experts[]` (max 20 rows) — cột Topic = `thread_url` |
| Top lô cao thủ | derived từ `live_experts` (STL/BTL, sort W) |
| Top lô đồng thuận | `consensus.loto_top10[]` |

Pick chips (BTL, bao, xiên, đề, chạm) SHALL có tooltip/popup “ai chốt” (`pick-who-popup`).

3 section có nút thu/gộp: Chốt đề theo cao thủ, Dàn đề, Gợi ý loại trừ.

**Scenario: Chưa có cao thủ**
- THEN `live_experts` empty message: "Chưa có cao thủ chốt (poll + sync API)"

**Scenario: Sau 18:30**
- THEN hint xanh: đề xuất dùng pick mới (thảo luận + chăn nuôi)

---

### REQ-RT-004: Response schema (`RecommendationsResponse`)

Popup types trong `recommendations-api.ts` SHALL khớp backend `forum_recommendation_service.build_recommendations()`:

```ts
{
  target_date: string;
  source: "forum";
  confidence: number;
  expert_count: number;
  has_forum_session: boolean;
  picks: { btl_lo, bao_lo_9, xien_2, de_top_4 };
  consensus?: {
    picks: { btl_lo, bao_lo_9, xien_2, de_top_4 };
    loto_top10: ForumLotoRow[];
    de_cham: ConsensusChamRow[];
    stats?: ConsensusStats;
  };
  de_cham_leaders: DeChamLeader[];
  dan_board: DanBoardRow[];
  de_by_expert?: DeByExpertRow[];
  forum_loto_top10: ForumLotoRow[];
  live_experts: LiveExpertRow[];
}
```

`LiveExpertRow` MAY include `thread_id`, `thread_url`, `forum`, `posted_at`.

---

### REQ-RT-005: Settings panel

Auth + API settings SHALL nằm trong panel ⚙️ (collapsible), không che tab Đề xuất.

Khi đã login forum: hiện hint "Đã đăng nhập", vẫn hiện username/password (masked).

Popup width ~680px; bảng dùng `.reco-table` (`display: table`).
