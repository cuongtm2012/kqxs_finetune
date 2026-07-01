import type { RecommendationsResponse, ConsensusChamRow, ConsensusStats, DeByExpertRow } from "../lib/recommendations-api.js";
import { fetchRecommendationsAndSyncUrl } from "../lib/recommendations-api.js";
import { pushSessionToApi } from "../lib/api-client.js";
import { getCollectWindow, getTargetDate } from "../lib/date-window.js";
import {
  clearSession,
  getForumAuth,
  getRuntimeStatus,
  getSession,
  getSettings,
  listSessionDates,
  saveForumAuth,
  saveSettings,
} from "../lib/storage.js";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

function badgeClass(status: string): string {
  const map: Record<string, string> = {
    collecting: "collecting",
    finalized: "finalized",
    waiting_thread: "waiting",
    sunday_skip: "sunday",
    idle: "idle",
  };
  return map[status] || "idle";
}

function authLabel(status: string): string {
  const map: Record<string, string> = {
    logged_in: "Đã đăng nhập",
    not_logged_in: "Chưa đăng nhập",
    checking: "Đang kiểm tra…",
    error: "Lỗi đăng nhập",
  };
  return map[status] || status;
}

async function send(type: string, payload: Record<string, unknown> = {}) {
  return chrome.runtime.sendMessage({ type, ...payload });
}

const RECO_LOADING_STEPS = [
  "Sync session lên API…",
  "Kết nối API…",
  "Lấy pick cao thủ…",
  "Tổng hợp dàn đề…",
  "Tính top lô…",
];

let recoLoadingTimer: ReturnType<typeof setInterval> | null = null;
let recoLoading = false;

function setRecoLoading(active: boolean, step?: string): void {
  recoLoading = active;
  const panel = $("panel-reco");
  const box = $("reco-loading");
  const btn = $("btn-refresh-reco");
  const label = btn.querySelector(".btn-label");

  panel.classList.toggle("is-loading", active);
  box.classList.toggle("hidden", !active);
  box.hidden = !active;
  box.setAttribute("aria-busy", String(active));
  btn.disabled = active;
  btn.classList.toggle("loading", active);
  if (label) label.textContent = active ? "Đang tải…" : "Tải đề xuất";
  if (step) $("reco-loading-text").textContent = step;
}

function startRecoLoadingAnimation(): void {
  let step = 0;
  setRecoLoading(true, RECO_LOADING_STEPS[0]);
  recoLoadingTimer = setInterval(() => {
    step = (step + 1) % RECO_LOADING_STEPS.length;
    $("reco-loading-text").textContent = RECO_LOADING_STEPS[step];
  }, 700);
}

function stopRecoLoadingAnimation(): void {
  if (recoLoadingTimer) {
    clearInterval(recoLoadingTimer);
    recoLoadingTimer = null;
  }
  setRecoLoading(false);
}

function setTab(name: "collect" | "reco"): void {
  const collect = name === "collect";
  $("tab-collect").classList.toggle("active", collect);
  $("tab-reco").classList.toggle("active", !collect);
  $("tab-collect").setAttribute("aria-selected", String(collect));
  $("tab-reco").setAttribute("aria-selected", String(!collect));
  $("panel-collect").classList.toggle("hidden", !collect);
  $("panel-collect").hidden = !collect;
  $("panel-reco").classList.toggle("hidden", collect);
  $("panel-reco").hidden = collect;
  if (!collect && !recoLoading) void loadRecommendations();
}

const DE_PICK_TYPES = new Set(["de_cham", "de_dau", "de_tong", "btd", "btd_dau"]);

const PICK_LABELS: Record<string, string> = {
  stl: "STL",
  btl: "BTL",
  de_dau: "Đề đầu",
  de_cham: "Chạm",
  de_tong: "Tổng",
  btd: "BTD",
  btd_dau: "Đầu ĐB",
  muc_lo: "Mức lô",
};

function fmtForumTag(f?: string | null): string {
  if (f === "thao_luan") return "TL";
  if (f === "chan_nuoi") return "CN";
  if (f === "mo_bat") return "MB";
  return "";
}

function buildDeByExpertRows(data: RecommendationsResponse): DeByExpertRow[] {
  const byUser = new Map<string, DeByExpertRow>();

  const ensure = (user: string): DeByExpertRow => {
    let row = byUser.get(user);
    if (!row) {
      row = {
        user,
        dan_size: null,
        dan_count: 0,
        dan_preview: [],
        de_cham: [],
        de_dau: [],
        de_tong: [],
        btd: [],
        btd_dau: [],
        forum: null,
        weight: 0,
        performance: null,
      };
      byUser.set(user, row);
    }
    return row;
  };

  for (const r of data.de_by_expert || []) {
    const row = ensure(r.user);
    Object.assign(row, r);
  }

  for (const d of data.dan_board || []) {
    const row = ensure(d.user);
    row.dan_size = d.size;
    row.dan_count = d.count;
    row.dan_preview = (d.numbers || []).slice(0, 8).map((n) => String(n).padStart(2, "0"));
    row.weight = Math.max(row.weight, d.weight);
    row.performance = d.performance ?? row.performance;
    if (d.forum) row.forum = d.forum;
  }

  for (const le of data.live_experts || []) {
    if (!DE_PICK_TYPES.has(le.pick_type)) continue;
    const row = ensure(le.user);
    const nums = le.numbers.map((n) =>
      le.pick_type === "btd" ? String(n).padStart(2, "0") : String(n),
    );
    if (le.pick_type === "de_cham") row.de_cham = nums;
    else if (le.pick_type === "de_dau") row.de_dau = nums;
    else if (le.pick_type === "de_tong") row.de_tong = nums;
    else if (le.pick_type === "btd") row.btd = nums;
    else if (le.pick_type === "btd_dau") row.btd_dau = nums;
    row.weight = Math.max(row.weight, le.weight);
    row.performance = le.performance ?? row.performance;
    if (le.forum) row.forum = le.forum;
  }

  for (const c of data.de_cham_leaders || []) {
    const row = ensure(c.user);
    if (!row.de_cham.length) row.de_cham = c.cham;
  }

  return [...byUser.values()]
    .filter(
      (r) =>
        r.dan_count > 0 ||
        r.de_cham.length > 0 ||
        r.de_dau.length > 0 ||
        r.de_tong.length > 0 ||
        r.btd.length > 0 ||
        r.btd_dau.length > 0,
    )
    .sort((a, b) => b.weight - a.weight || b.dan_count - a.dan_count || a.user.localeCompare(b.user));
}

function hasDePicks(r: DeByExpertRow): boolean {
  return (
    r.btd.length > 0 ||
    r.btd_dau.length > 0 ||
    r.de_cham.length > 0 ||
    r.de_dau.length > 0 ||
    r.de_tong.length > 0
  );
}

function isDanOnly(r: DeByExpertRow): boolean {
  return r.dan_count > 0 && !hasDePicks(r);
}

function compactPickLine(r: DeByExpertRow): string {
  const parts: string[] = [];
  if (r.btd.length) parts.push(`BTD ${r.btd.join(",")}`);
  if (r.btd_dau.length) parts.push(`ĐầuĐB ${r.btd_dau.join(",")}`);
  if (r.de_cham.length) parts.push(`Chạm ${r.de_cham.join(",")}`);
  if (r.de_dau.length) parts.push(`Đầu ${r.de_dau.join(",")}`);
  if (r.de_tong.length) parts.push(`Tổng ${r.de_tong.join(",")}`);
  if (r.dan_count && !hasDePicks(r)) parts.push(`${r.dan_size || "dàn"} ${r.dan_count}s`);
  return parts.join(" · ") || "—";
}

function renderDeByExpert(data: RecommendationsResponse): void {
  const el = $("reco-de-by-expert");
  const list = buildDeByExpertRows(data);

  if (!list.length) {
    el.innerHTML =
      "<p class='muted'>Chưa có chốt đề (poll chăn nuôi / thảo luận + sync API)</p>";
    return;
  }

  const pickRows = list.filter((r) => hasDePicks(r) || r.forum === "thao_luan");
  const danOnly = list.filter(isDanOnly);

  const renderCompactRow = (r: DeByExpertRow): string => {
    const tag = fmtForumTag(r.forum);
    return `<div class="de-compact-row" data-user="${r.user}">
      <button type="button" class="link-btn de-jump" data-user="${r.user}">${r.user}</button>
      ${tag ? `<span class="forum-tag forum-tag-${tag.toLowerCase()}">${tag}</span>` : ""}
      <span class="de-compact-picks nums">${compactPickLine(r)}</span>
      <span class="muted de-compact-w">w${r.weight}</span>
    </div>`;
  };

  let html = "";

  if (pickRows.length) {
    html += `<div class="de-expert-group">
      <h3 class="de-expert-group-title">Chốt đề / thảo luận (${pickRows.length})</h3>
      ${pickRows.map(renderCompactRow).join("")}
    </div>`;
  }

  if (danOnly.length) {
    const sizes = [...new Set(danOnly.map((r) => r.dan_size || "dàn"))].join("/");
    html += `<details class="de-dan-summary">
      <summary>Chăn nuôi · ${danOnly.length} dàn (${sizes})</summary>
      <div class="de-dan-summary-list">${danOnly.map(renderCompactRow).join("")}</div>
    </details>`;
  }

  el.innerHTML = html;
}

function setupDeJumpHandlers(): void {
  $("reco-de-by-expert").addEventListener("click", (ev) => {
    const btn = (ev.target as HTMLElement | null)?.closest?.("button.de-jump") as HTMLButtonElement | null;
    if (!btn) return;
    const user = btn.getAttribute("data-user");
    if (!user) return;
    const card = document.querySelector(`details.dan-card[data-user="${CSS.escape(user)}"]`) as HTMLDetailsElement | null;
    if (card) {
      card.open = true;
      card.scrollIntoView({ behavior: "smooth", block: "nearest" });
      card.classList.add("dan-card-focus");
      window.setTimeout(() => card.classList.remove("dan-card-focus"), 2000);
      return;
    }
    const pickRow = document.querySelector(
      `#reco-experts-rows tr[data-user="${CSS.escape(user)}"]`,
    ) as HTMLTableRowElement | null;
    if (pickRow) {
      pickRow.scrollIntoView({ behavior: "smooth", block: "nearest" });
      pickRow.classList.add("row-focus");
      window.setTimeout(() => pickRow.classList.remove("row-focus"), 2000);
    }
  });
}

function renderDanBoard(rows: RecommendationsResponse["dan_board"]): void {
  const el = $("reco-dan-board");
  if (!rows?.length) {
    el.innerHTML = "<p>Chưa có dàn 40s/36s/64s (poll topic chăn nuôi + sync API)</p>";
    $("reco-dan-filter").innerHTML = "<p>Chưa có dàn để lọc.</p>";
    return;
  }

  // Unique cao thủ per number (not dan-row count — one user = one vote)
  const usersByNum = new Map<string, Set<string>>();
  for (const r of rows) {
    for (const n of r.numbers || []) {
      const key = String(n).padStart(2, "0");
      const set = usersByNum.get(key) || new Set<string>();
      set.add(r.user);
      usersByNum.set(key, set);
    }
  }
  const totalUsers = new Set(rows.map((r) => r.user)).size;
  const overlapUsers = (n: string): number => usersByNum.get(n)?.size ?? 0;
  // Skip near-universal numbers (e.g. 6/7 or 7/7) — highlight loses meaning on large overlapping dans
  const isMeaningfulOverlap = (n: string): boolean => {
    const u = overlapUsers(n);
    if (u < 2) return false;
    if (u >= totalUsers) return false;
    if (totalUsers >= 4 && u >= totalUsers - 1) return false;
    return true;
  };

  const order = ["40s", "36s", "64s", "dàn"];
  const grouped = new Map<string, typeof rows>();
  for (const r of rows) {
    const list = grouped.get(r.size) || [];
    list.push(r);
    grouped.set(r.size, list);
  }

  const fmtPerf = (p?: { hits: number; total: number; rate_pct: number } | null): string => {
    if (!p?.total) return "—";
    return `${p.rate_pct}% (${p.hits}/${p.total})`;
  };

  const renderNums = (nums: string[]): string =>
    (nums || [])
      .map((raw) => {
        const n = String(raw).padStart(2, "0");
        const u = overlapUsers(n);
        if (isMeaningfulOverlap(n)) {
          return `<span class="dan-num overlap" data-cnt="${u}" title="Trùng ${u}/${totalUsers} cao thủ">${n}</span>`;
        }
        return `<span class="dan-num">${n}</span>`;
      })
      .join(", ");

  const overlapOnly = (nums: string[]): string[] =>
    (nums || [])
      .map((raw) => String(raw).padStart(2, "0"))
      .filter((n) => isMeaningfulOverlap(n));

  el.innerHTML = order
    .filter((sz) => grouped.has(sz))
    .map((sz) => {
      const cards = (grouped.get(sz) || [])
        .map(
          (d) =>
            `<details class="dan-card" data-user="${d.user}">
              <summary>
                <span class="dan-summary-user">${d.user}</span>
                <span class="muted"> · ${d.size} · ${d.count} số · w=${d.weight} · perf ${fmtPerf(d.performance)}</span>
                <span class="dan-summary-preview nums">${(d.numbers || []).slice(0, 12).map((n) => String(n).padStart(2, "0")).join(", ")}${d.count > 12 ? ` …+${d.count - 12}` : ""}</span>
              </summary>
              <div class="dan-card-actions">
                <button class="dan-copy" type="button" title="Copy dàn" data-copy="all" data-user="${d.user}" data-nums="${(d.numbers || []).join(",")}">Copy</button>
                <button class="dan-copy dan-copy-overlap" type="button" title="Copy số trùng" data-copy="overlap" data-user="${d.user}" data-nums="${overlapOnly(d.numbers).join(",")}">Trùng</button>
              </div>
              <div class="dan-nums">${renderNums(d.numbers)}</div>
            </details>`,
        )
        .join("");
      return `<div><strong>Dàn ${sz}</strong><p class="muted dan-hint">Highlight: số ≥2 cao thủ chốt (bỏ số gần như ai cũng có)</p>${cards}</div>`;
    })
    .join("");

  // Filter / exclusion suggestion using dan performance
  const filterEl = $("reco-dan-filter");
  const strong: string[] = [];
  const weak: string[] = [];
  for (const r of rows) {
    const p = r.performance;
    if (!p?.total || p.total < 3) continue;
    if (p.rate_pct >= 70) strong.push(r.user);
    if (p.rate_pct <= 40) weak.push(r.user);
  }

  const weakSet = new Set(weak);
  const strongSet = new Set(strong);

  const kept = new Map<string, number>();
  const excluded = new Map<string, number>();

  for (const r of rows) {
    const user = r.user;
    const isStrong = strongSet.has(user);
    const isWeak = weakSet.has(user);
    for (const raw of r.numbers || []) {
      const n = String(raw).padStart(2, "0");
      if (isStrong) kept.set(n, (kept.get(n) || 0) + 1);
      if (isWeak) excluded.set(n, (excluded.get(n) || 0) + 1);
    }
  }

  const result = [...kept.keys()].filter((n) => !excluded.has(n));
  result.sort((a, b) => (kept.get(b)! - kept.get(a)!) || a.localeCompare(b));

  if (!strong.length && !weak.length) {
    filterEl.innerHTML =
      "<p class='muted'>Chưa đủ dữ liệu hiệu suất (cần ≥3 mẫu) để lọc loại trừ.</p>";
  } else {
    const keptNums = result.slice(0, 60).join(", ") || "—";
    filterEl.innerHTML = `
      <div><span class="tag good">Cao (≥70% · ≥3 mẫu)</span>${strong.length ? strong.join(", ") : "—"}</div>
      <div style="margin-top:6px;"><span class="tag bad">Thấp (≤40% · ≥3 mẫu)</span>${weak.length ? weak.join(", ") : "—"}</div>
      <div style="margin-top:8px;"><strong>Giữ lại (cao − thấp):</strong> <span class="nums">${keptNums}</span></div>
    `;
  }
}

function setupDanCopyHandlers(): void {
  const root = $("reco-dan-board");
  root.addEventListener("click", async (ev) => {
    const t = ev.target as HTMLElement | null;
    const btn = t?.closest?.("button.dan-copy") as HTMLButtonElement | null;
    if (!btn) return;
    const nums = (btn.getAttribute("data-nums") || "").trim();
    if (!nums) return;
    try {
      await navigator.clipboard.writeText(nums);
      const prev = btn.textContent || "";
      btn.textContent = "Đã copy";
      setTimeout(() => {
        btn.textContent = prev;
      }, 900);
    } catch {
      // fallback for restricted clipboard
      const ta = document.createElement("textarea");
      ta.value = nums;
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
  });
}

function formatPerformance(perf?: { hits: number; total: number; rate_pct: number } | null): string {
  if (!perf?.total) return "—";
  return `${perf.rate_pct}% (${perf.hits}/${perf.total})`;
}

function formatConsensusCham(rows: ConsensusChamRow[] | undefined): string {
  if (!rows?.length) return "—";
  return rows
    .slice(0, 6)
    .map((c) => `${c.cham} (${c.votes}: ${c.users.join(", ")})`)
    .join(" · ");
}

function formatBaoWithVotes(
  nums: string[],
  voteMap: Map<string, number>,
): string {
  if (!nums.length) return "—";
  return nums
    .map((n) => {
      const v = voteMap.get(n);
      return v && v >= 2 ? `${n}×${v}` : n;
    })
    .join(", ");
}

function buildVoteMap(rows: { loto: string; score: number; votes?: number }[]): Map<string, number> {
  const m = new Map<string, number>();
  for (const r of rows) {
    m.set(r.loto, Math.round(r.votes ?? r.score));
  }
  return m;
}

function renderConsensusHint(stats?: ConsensusStats): void {
  const el = $("reco-consensus-hint");
  const s = stats;
  if (!s) {
    el.classList.add("hidden");
    el.hidden = true;
    return;
  }
  el.hidden = false;
  el.classList.remove("hidden", "strong");
  if (s.has_strong_consensus) {
    el.classList.add("strong");
    el.textContent = `Có ${s.strong_loto_count} số được ≥2 cao thủ chốt (mạnh nhất: ${s.max_votes} phiếu). Trùng bao lô với panel trọng số: ${s.bao_lo_overlap}/9.`;
  } else {
    el.textContent =
      `Chưa có số nào ≥2 cao thủ — đồng thuận xếp ngược trọng số (ưu tiên cao thủ ít w). Trùng bao lô: ${s.bao_lo_overlap_pct}%.`;
  }
}

function renderRecommendations(data: RecommendationsResponse): void {
  $("reco-expert-count").textContent = String(data.expert_count ?? data.live_experts.length);

  const voteMap = buildVoteMap(data.consensus?.loto_top10 || []);
  const expertBao = data.picks.bao_lo_9;
  const consensusBao = data.consensus?.picks?.bao_lo_9 || [];
  const consensusSet = new Set(consensusBao);

  $("reco-btl").textContent = data.picks.btl_lo || "—";
  $("reco-bao").textContent = expertBao.join(", ") || "—";
  $("reco-xien").textContent = data.picks.xien_2.join(" / ") || "—";
  $("reco-de").textContent = data.picks.de_top_4.join(", ") || "—";

  const cham = data.de_cham_leaders || [];
  $("reco-cham").textContent = cham.length
    ? cham.map((c) => `${c.user}: ${c.cham.join(",")}`).join(" · ")
    : "—";

  const consensus = data.consensus;
  if (consensus?.picks) {
    $("reco-consensus-btl").textContent = consensus.picks.btl_lo || "—";
    $("reco-consensus-bao").textContent = formatBaoWithVotes(consensusBao, voteMap);
    $("reco-consensus-xien").textContent = consensus.picks.xien_2.join(" / ") || "—";
    $("reco-consensus-de").textContent = consensus.picks.de_top_4.join(", ") || "—";
    $("reco-consensus-cham").textContent = formatConsensusCham(consensus.de_cham);
    renderConsensusHint(consensus.stats);
  } else {
    $("reco-consensus-btl").textContent = "—";
    $("reco-consensus-bao").textContent = "—";
    $("reco-consensus-xien").textContent = "—";
    $("reco-consensus-de").textContent = "—";
    $("reco-consensus-cham").textContent = "—";
    $("reco-consensus-hint").classList.add("hidden");
    $("reco-consensus-hint").hidden = true;
  }

  // Đánh dấu số chỉ có ở 1 panel
  if (consensusBao.length && expertBao.join() !== consensusBao.join()) {
    $("reco-bao").innerHTML = expertBao
      .map((n) =>
        consensusSet.has(n)
          ? `<span>${n}</span>`
          : `<span class="nums-diff" title="Chỉ panel trọng số">${n}</span>`,
      )
      .join(", ");
    $("reco-consensus-bao").innerHTML = consensusBao
      .map((n) => {
        const v = voteMap.get(n);
        const label = v && v >= 2 ? `${n}×${v}` : n;
        return expertBao.includes(n)
          ? `<span>${label}</span>`
          : `<span class="nums-diff" title="Chỉ panel đồng thuận">${label}</span>`;
      })
      .join(", ");
  }

  renderDeByExpert(data);
  renderDanBoard(data.dan_board || []);

  const tbody = $("reco-experts-rows");
  if (!data.live_experts.length) {
    tbody.innerHTML = "<tr><td colspan='6' class='muted'>Chưa có cao thủ chốt (poll + sync API)</td></tr>";
  } else {
    tbody.innerHTML = data.live_experts
      .slice(0, 20)
      .map(
        (e) => {
          const tag = fmtForumTag(e.forum);
          const label = PICK_LABELS[e.pick_type] || e.pick_type;
          return `<tr data-user="${e.user}" data-forum="${e.forum || ""}">
            <td><strong>${e.user}</strong></td>
            <td>${tag ? `<span class="forum-tag forum-tag-${tag.toLowerCase()}">${tag}</span>` : "—"}</td>
            <td>${label}</td>
            <td class="nums">${e.numbers.join(", ")}</td>
            <td>${formatPerformance(e.performance)}</td>
            <td>${e.weight}</td>
          </tr>`;
        },
      )
      .join("");
  }

  const rows = data.forum_loto_top10 || [];
  const lotoBody = $("reco-loto-rows");
  if (!rows.length) {
    lotoBody.innerHTML = "<tr><td colspan='4' class='muted'>Chưa có lô từ cao thủ</td></tr>";
  } else {
    lotoBody.innerHTML = rows
      .map(
        (r, i) =>
          `<tr><td>${i + 1}</td><td><strong>${r.loto}</strong></td><td>${r.score.toFixed(2)}</td><td>${r.users.join(", ") || "—"}</td></tr>`,
      )
      .join("");
  }

  const consensusRows = consensus?.loto_top10 || [];
  const consensusBody = $("reco-consensus-loto-rows");
  if (!consensusRows.length) {
    consensusBody.innerHTML = "<tr><td colspan='4' class='muted'>Chưa có lô đồng thuận</td></tr>";
  } else {
    consensusBody.innerHTML = consensusRows
      .map((r, i) => {
        const votes = Math.round(r.votes ?? r.score);
        const voteLabel = votes >= 2 ? `${votes}★` : String(votes);
        return `<tr><td>${i + 1}</td><td><strong>${r.loto}</strong></td><td>${voteLabel}</td><td>${r.users.join(", ") || "—"}</td></tr>`;
      })
      .join("");
  }

  $("reco-error").classList.add("hidden");
}

async function loadRecommendations(): Promise<void> {
  if (recoLoading) return;

  const settings = await getSettings();
  const runtime = await getRuntimeStatus();
  const target =
    runtime.target_date || getTargetDate(new Date(), settings.timezone);

  $("reco-error").classList.add("hidden");
  startRecoLoadingAnimation();

  try {
    const session = await getSession(target);
    if (session) {
      $("reco-loading-text").textContent = "Đang sync session lên API…";
      await pushSessionToApi(session, { force: true });
    }

    const data = await fetchRecommendationsAndSyncUrl(target, settings);
    if (!session && !data.has_forum_session && data.expert_count === 0) {
      throw new Error(
        "Chưa có dữ liệu cao thủ — poll forum trước (tab Thu thập), rồi bấm Tải đề xuất",
      );
    }
    $("reco-loading-text").textContent = "Hoàn tất!";
    renderRecommendations(data);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    const err = $("reco-error");
    err.textContent = msg;
    err.classList.remove("hidden");
  } finally {
    stopRecoLoadingAnimation();
  }
}

async function refreshUi(): Promise<void> {
  const settings = await getSettings();
  const runtime = await getRuntimeStatus();
  const auth = await getForumAuth();
  const target = runtime.target_date || getTargetDate(new Date(), settings.timezone);
  const { window_start, window_end } = getCollectWindow(target, settings.timezone);

  const badge = $("status-badge");
  badge.textContent = runtime.collect_status;
  badge.className = `badge ${badgeClass(runtime.collect_status)}`;

  $("target-date").textContent = target;
  $("window-range").textContent = `${window_start} → ${window_end}`;
  $("post-count").textContent = String(runtime.post_count);
  $("new-posts").textContent = String(runtime.new_posts_last_poll);
  $("last-poll").textContent = runtime.last_poll_at
    ? new Date(runtime.last_poll_at).toLocaleString("vi-VN")
    : "—";
  $("last-poll-status").textContent = runtime.last_poll_status || "—";

  $("auth-status-short").textContent = authLabel(runtime.auth_status);
  const authCard = $("auth-card");
  const loggedIn = runtime.auth_status === "logged_in";
  authCard.classList.toggle("logged-in", loggedIn);
  $("auth-logged-hint").classList.toggle("hidden", !loggedIn);
  ($("auth-user") as HTMLInputElement).value = auth.username;
  ($("auth-pass") as HTMLInputElement).value = auth.password;
  ($("api-url") as HTMLInputElement).value = settings.api_base_url;
  ($("auto-sync") as HTMLInputElement).checked = settings.auto_sync;
  ($("poll-active") as HTMLInputElement).value = String(settings.poll_interval_active_min);

  const err = $("error");
  if (runtime.last_error) {
    err.textContent = runtime.last_error;
    err.classList.remove("hidden");
  } else {
    err.classList.add("hidden");
  }
}

$("tab-collect").addEventListener("click", () => setTab("collect"));
$("tab-reco").addEventListener("click", () => setTab("reco"));
$("btn-refresh-reco").addEventListener("click", () => loadRecommendations());

setupDanCopyHandlers();
setupDeJumpHandlers();

$("btn-poll").addEventListener("click", async () => {
  $("btn-poll").textContent = "Đang poll…";
  await send("POLL_NOW");
  await refreshUi();
  $("btn-poll").textContent = "Poll ngay";
});

$("btn-login").addEventListener("click", async () => {
  $("btn-login").textContent = "…";
  await send("LOGIN");
  await refreshUi();
  $("btn-login").textContent = "Đăng nhập lại";
});

$("btn-save-auth").addEventListener("click", async () => {
  await saveForumAuth({
    username: ($("auth-user") as HTMLInputElement).value.trim(),
    password: ($("auth-pass") as HTMLInputElement).value,
  });
  await saveSettings({
    api_base_url: ($("api-url") as HTMLInputElement).value.trim(),
    auto_sync: ($("auto-sync") as HTMLInputElement).checked,
    poll_interval_active_min: Number(($("poll-active") as HTMLInputElement).value) || 5,
  });
  await send("SETUP_ALARMS");
  await refreshUi();
});

$("btn-export").addEventListener("click", async () => {
  const settings = await getSettings();
  const target = getTargetDate(new Date(), settings.timezone);
  const session = await getSession(target);
  if (!session) {
    alert("Chưa có session cho ngày này.");
    return;
  }
  const blob = new Blob([JSON.stringify(session, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  await chrome.downloads.download({
    url,
    filename: `rbk-forum-${target}.json`,
    saveAs: true,
  });
  URL.revokeObjectURL(url);
});

$("btn-clear").addEventListener("click", async () => {
  const settings = await getSettings();
  const target = getTargetDate(new Date(), settings.timezone);
  if (!confirm(`Xóa session ${target}?`)) return;
  await clearSession(target);
  await refreshUi();
  void listSessionDates();
});

const settingsPanel = $("settings-panel");
const toggleSettingsBtn = $("btn-toggle-settings");

function setSettingsOpen(open: boolean): void {
  settingsPanel.classList.toggle("hidden", !open);
  settingsPanel.hidden = !open;
  toggleSettingsBtn.setAttribute("aria-expanded", String(open));
}

toggleSettingsBtn.addEventListener("click", () => {
  setSettingsOpen(settingsPanel.hidden);
});

async function maybeOpenSettingsForAuth(): Promise<void> {
  const runtime = await getRuntimeStatus();
  if (runtime.auth_status === "not_logged_in" || runtime.auth_status === "error") {
    setSettingsOpen(true);
  }
}

void maybeOpenSettingsForAuth();
refreshUi();
setInterval(refreshUi, 5000);
