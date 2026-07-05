import type {
  ConsensusChamRow,
  ConsensusStats,
  DeByExpertRow,
  LiveExpertRow,
  RecommendationsResponse,
} from "../lib/recommendations-api.js";
import { fetchRecommendationsAndSyncUrl } from "../lib/recommendations-api.js";
import type { DrawScoreResponse } from "../lib/score-api.js";
import { fetchDrawScore, runDrawScore } from "../lib/score-api.js";
import { pushSessionToApi } from "../lib/api-client.js";
import { ensureApiOnline, resolveWorkingApiBase } from "../lib/api-base.js";
import { getCalendarDate, getCollectWindow, getLatestDrawScoreDate, getTargetDate, isAfterDrawSettlement, isAfterResultCutoff } from "../lib/date-window.js";
import type { EngineBundle } from "../lib/engine-api.js";
import { fetchEngineBundle } from "../lib/engine-api.js";
import type { ScoringMode } from "../lib/recommendations-api.js";
import {
  clearSession,
  ensureConfigSeeded,
  getForumAuth,
  getRuntimeStatus,
  getSession,
  getSettings,
  getRecoExpertSort,
  getRecoScoringMode,
  listSessionDates,
  saveRecoExpertSort,
  saveRecoScoringMode,
} from "../lib/storage.js";
import type { CollectSession } from "../types/forum.js";
import type { RecoExpertSortMode, RecoScoringMode } from "../lib/storage.js";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

/** Escape HTML special chars to prevent XSS in innerHTML. */
function esc(s: string | number | undefined | null): string {
  if (s === null || s === undefined) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function badgeClass(status: string): string {
  const map: Record<string, string> = {
    collecting: "collecting",
    backfilling: "collecting",
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

function collectStatusLabel(status: string): string {
  const map: Record<string, string> = {
    idle: "Chờ",
    collecting: "Đang thu thập",
    backfilling: "Đang backfill",
    finalized: "Đã chốt",
    waiting_thread: "Chờ topic",
    sunday_skip: "Đang thu thập",
  };
  return map[status] || status;
}

function pollStatusLabel(status: string): string {
  const map: Record<string, string> = {
    collecting: "Đang thu thập",
    login_failed: "Đăng nhập thất bại",
    waiting_thread: "Chưa có topic thảo luận",
    outside_window: "Ngoài khung giờ",
    finalized: "Đã chốt",
    finalized_coverage_warning: "Đã chốt (thiếu backfill)",
    backfilling: "Đang backfill trang cũ",
    sunday_skip: "Đang thu thập",
    rolled_over: "Đã chuyển ngày quay",
  };
  return map[status] || status;
}

function maskPassword(password: string): string {
  if (!password) return "—";
  if (password.length <= 2) return "••";
  return `${password.slice(0, 1)}${"•".repeat(Math.min(password.length - 1, 8))}`;
}

async function send(type: string, payload: Record<string, unknown> = {}) {
  return chrome.runtime.sendMessage({ type, ...payload });
}

const POLL_TIMEOUT_MS = 45_000;

async function pollNowWithTimeout(ms = POLL_TIMEOUT_MS): Promise<unknown> {
  return Promise.race([
    send("POLL_NOW"),
    new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error("Poll timeout")), ms),
    ),
  ]);
}

async function syncSessionOptional(
  session: CollectSession,
  force: boolean,
): Promise<boolean> {
  try {
    return await pushSessionToApi(session, { force });
  } catch {
    return false;
  }
}

function sessionPostCount(session?: CollectSession): number {
  return session ? Object.keys(session.posts).length : 0;
}

function thaoLuanPostCount(session?: CollectSession): number {
  if (!session) return 0;
  return Object.values(session.posts).filter((p) => p.forum === "thao_luan").length;
}

function needsPollForTarget(
  target: string,
  runtime: Awaited<ReturnType<typeof getRuntimeStatus>>,
  session: CollectSession | undefined,
  afterCutoff: boolean,
): boolean {
  if (!afterCutoff) return false;
  if (runtime.target_date !== target) return true;
  if (sessionPostCount(session) === 0) return true;
  if (thaoLuanPostCount(session) === 0) return true;
  return false;
}

function formatTargetDateLabel(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
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
let lastRecoTarget = "";
let engineLoading = false;
let scoreLoading = false;

function setScoreLoading(active: boolean): void {
  scoreLoading = active;
  const btn = $("btn-refresh-score");
  const runBtn = $("btn-run-score");
  const label = btn.querySelector(".btn-label");
  btn.disabled = active;
  runBtn.disabled = active;
  btn.classList.toggle("loading", active);
  runBtn.classList.toggle("loading", active);
  if (label) label.textContent = active ? "Đang tải…" : "Tải kết quả";
}

type TabName = "collect" | "reco" | "engine" | "score";

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

function setEngineLoading(active: boolean, step?: string): void {
  engineLoading = active;
  const panel = $("panel-engine");
  const box = $("engine-loading");
  const btn = $("btn-refresh-engine");
  const label = btn.querySelector(".btn-label");

  panel.classList.toggle("is-loading", active);
  box.classList.toggle("hidden", !active);
  box.hidden = !active;
  box.setAttribute("aria-busy", String(active));
  btn.disabled = active;
  btn.classList.toggle("loading", active);
  if (label) label.textContent = active ? "Đang tải…" : "Tải engine";
  if (step) $("engine-loading-text").textContent = step;
}

function setTab(name: TabName): void {
  const tabIds: Record<TabName, { tab: string; panel: string }> = {
    collect: { tab: "tab-collect", panel: "panel-collect" },
    reco: { tab: "tab-reco", panel: "panel-reco" },
    engine: { tab: "tab-engine", panel: "panel-engine" },
    score: { tab: "tab-score", panel: "panel-score" },
  };

  for (const [tab, active] of Object.entries({
    collect: name === "collect",
    reco: name === "reco",
    engine: name === "engine",
    score: name === "score",
  }) as [TabName, boolean][]) {
    const ids = tabIds[tab];
    $(ids.tab).classList.toggle("active", active);
    $(ids.tab).setAttribute("aria-selected", String(active));
    const panel = $(ids.panel);
    panel.classList.toggle("hidden", !active);
    panel.hidden = !active;
  }

  if (name === "reco" && !recoLoading) void loadRecommendations();
  if (name === "engine" && !engineLoading) void loadEngine();
  if (name === "score" && !scoreLoading) void loadScore(false);
}

function getDrawScoreDate(now = new Date(), timeZone = "Asia/Ho_Chi_Minh"): string {
  return getLatestDrawScoreDate(now, timeZone);
}

function formatScoreNums(pickType: string, numbers: string[]): string {
  if (pickType === "std_de") return numbers.join(" / ");
  return numbers.join(", ");
}

function renderScore(data: DrawScoreResponse): void {
  $("score-target-date").textContent = formatTargetDateLabel(data.target_date);
  $("score-de").textContent = data.draw?.de || "—";
  $("score-db").textContent = data.draw?.db || "—";

  const summary = data.summary;
  $("score-summary").textContent = summary
    ? `${summary.hits}/${summary.total} (${summary.hit_rate_pct}%)`
    : "—";

  const hint = $("score-cutoff-hint");
  const postCount = data.coverage?.post_count;
  const baseHint = postCount != null
    ? `Chấm ${summary?.total ?? 0} pick từ Thu thập (${postCount} post). Chỉ tính pick chốt trước 18:00 (ICT).`
    : `Chỉ tính pick chốt trước 18:00 (ICT)`;
  if (data.cutoff) {
    hint.textContent = `${baseHint} · cutoff ${new Date(data.cutoff).toLocaleString("vi-VN")}`;
    hint.classList.remove("hidden");
  } else {
    hint.textContent = baseHint;
  }

  const covHint = $("score-coverage-hint");
  const incomplete = (data.coverage?.threads || []).filter((t) => t.backfill_complete === false);
  if (incomplete.length) {
    const parts = incomplete.map((t) => {
      const low = t.lowest_page_fetched ?? "?";
      const high = t.last_page_fetched ?? "?";
      const label = t.key === "thao_luan" ? "Thảo luận" : t.key === "mo_bat" ? "Mở bát" : t.key;
      return `${label}: ${low}/${high} trang`;
    });
    covHint.textContent = `⚠ Backfill chưa xong (${parts.join(", ")}) — có thể thiếu pick sớm. Poll ở tab Thu thập rồi Chấm lại.`;
    covHint.classList.remove("hidden", "ok");
    covHint.classList.add("warn");
    covHint.hidden = false;
  } else if (data.coverage?.coverage_warning) {
    covHint.textContent = "Session chốt khi backfill chưa hoàn tất — một số pick có thể thiếu.";
    covHint.classList.remove("hidden", "ok");
    covHint.classList.add("warn");
    covHint.hidden = false;
  } else {
    covHint.textContent = "";
    covHint.classList.add("hidden");
    covHint.hidden = true;
  }

  const tbody = $("score-rows");
  const rows = data.results || [];
  if (!data.ok || !rows.length) {
    const msg =
      data.error === "not_scored"
        ? "Chưa chấm — bấm Tải kết quả (sau 18:31 sẽ tự chấm) hoặc Chấm lại"
        : data.error === "no_draw"
          ? "Chưa có KQXS — thử Chấm lại (mketqua)"
          : "Chưa có dữ liệu đối chiếu";
    tbody.innerHTML = `<tr><td colspan="4" class="muted">${msg}</td></tr>`;
    return;
  }

  tbody.innerHTML = rows
    .map((r) => {
      const label = PICK_LABELS[r.pick_type] || r.pick_type;
      const nums = formatScoreNums(r.pick_type, r.numbers || []);
      // Build clickable num chips from score row data
      const numChips = (r.numbers || []).map((n) =>
        `<button type="button" class="pick-chip score-num-chip" data-score-num="${esc(n)}" data-score-user="${esc(r.username)}" title="${esc(r.username)} chốt ${n}">${esc(n)}</button>`
      ).join(", ");
      const kq = r.hit
        ? `<span class="score-hit">TRÚNG</span>`
        : `<span class="score-miss">trượt</span>`;
      return `<tr class="${r.hit ? "row-hit" : ""}">
        <td><strong>${esc(r.username)}</strong></td>
        <td>${esc(label)}</td>
        <td class="nums">${numChips || "—"}</td>
        <td>${kq}</td>
      </tr>`;
    })
    .join("");
}

async function loadScore(forceRun: boolean): Promise<void> {
  if (scoreLoading) return;
  setScoreLoading(true);
  const now = new Date();
  $("score-error").classList.add("hidden");

  try {
    const settings = await ensureApiOnline(await getSettings());
    let drawDate = getDrawScoreDate(now, settings.timezone);

    let data = forceRun
      ? await runDrawScore(drawDate, settings)
      : await fetchDrawScore(drawDate, settings);

    if (
      !forceRun &&
      !data.ok &&
      data.error === "not_scored" &&
      isAfterDrawSettlement(now, settings.timezone)
    ) {
      data = await runDrawScore(drawDate, settings);
    }

    if (!forceRun && !data.ok && data.error === "not_scored") {
      const [y, m, d] = drawDate.split("-").map(Number);
      const prev = new Date(Date.UTC(y, m - 1, d));
      prev.setUTCDate(prev.getUTCDate() - 1);
      const fallback = `${prev.getUTCFullYear()}-${String(prev.getUTCMonth() + 1).padStart(2, "0")}-${String(prev.getUTCDate()).padStart(2, "0")}`;
      const retry = await fetchDrawScore(fallback, settings);
      if (retry.ok) {
        data = retry;
        drawDate = fallback;
      }
    }

    renderScore(data);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    const err = $("score-error");
    err.textContent = msg;
    err.classList.remove("hidden");
  } finally {
    setScoreLoading(false);
  }
}

const DE_PICK_TYPES = new Set(["de_cham", "de_dau", "de_tong", "btd", "btd_dau", "std_de", "btd_de"]);
const LOTO_PICK_TYPES = new Set(["stl", "btl", "muc_lo"]);

const PICK_LABELS: Record<string, string> = {
  stl: "STL",
  btl: "BTL",
  std_de: "STĐ",
  btd_de: "BTĐ",
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
    await copyTextToClipboard(nums);
    await flashCopyButton(btn);
  });
}

function formatPerformance(perf?: { hits: number; total: number; rate_pct: number; low_sample?: boolean } | null): string {
  if (!perf?.total) return "—";
  const star = perf.low_sample ? "*" : "";
  return `${perf.rate_pct}% (${perf.hits}/${perf.total})${star}`;
}

function formatStlPair(nums: string[]): string {
  if (!nums.length) return "—";
  if (nums.length === 2) return `${nums[0]}-${nums[1]}`;
  return nums.join(", ");
}

interface TopLotoExpertRow {
  user: string;
  forum?: string;
  weight: number;
  performance?: LiveExpertRow["performance"];
  stl: string[];
  btl: string[];
}

function buildTopLotoExperts(experts: LiveExpertRow[]): TopLotoExpertRow[] {
  const byUser = new Map<string, TopLotoExpertRow>();

  for (const e of experts) {
    if (!LOTO_PICK_TYPES.has(e.pick_type)) continue;
    let row = byUser.get(e.user);
    if (!row) {
      row = {
        user: e.user,
        forum: e.forum,
        weight: e.weight,
        performance: e.performance,
        stl: [],
        btl: [],
      };
      byUser.set(e.user, row);
    }
    if (e.weight > row.weight) row.weight = e.weight;
    if (e.forum && !row.forum) row.forum = e.forum;
    if (e.performance?.total && (!row.performance?.total || e.performance.rate_pct > row.performance.rate_pct)) {
      row.performance = e.performance;
    }
    const nums = (e.numbers || []).map((n) => String(n).padStart(2, "0"));
    if (e.pick_type === "stl") {
      row.stl = nums.slice(0, 2);
    } else {
      for (const n of nums) {
        if (!row.btl.includes(n)) row.btl.push(n);
      }
    }
  }

  return [...byUser.values()]
    .filter((r) => r.stl.length > 0 || r.btl.length > 0)
    .sort((a, b) => b.weight - a.weight || a.user.localeCompare(b.user))
    .slice(0, 10);
}

function renderTopLotoExperts(experts: LiveExpertRow[]): void {
  const rows = buildTopLotoExperts(experts);
  const tbody = $("reco-loto-rows");
  if (!rows.length) {
    tbody.innerHTML = "<tr><td colspan='6' class='muted'>Chưa có cao thủ chốt lô</td></tr>";
    return;
  }
  tbody.innerHTML = rows
    .map((r, i) => {
      const tag = fmtForumTag(r.forum);
      const perf = formatPerformance(r.performance);
      const stl = formatStlPair(r.stl);
      const btl = r.btl.length ? r.btl.join(", ") : "—";
      return `<tr data-user="${r.user}">
        <td>${i + 1}</td>
        <td><strong>${r.user}</strong><br><span class="muted expert-loto-perf">${perf}</span></td>
        <td>${tag ? `<span class="forum-tag forum-tag-${tag.toLowerCase()}">${tag}</span>` : "—"}</td>
        <td class="nums">${stl}</td>
        <td class="nums">${btl}</td>
        <td>${r.weight.toFixed(2)}</td>
      </tr>`;
    })
    .join("");
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

type PickBucket = "btl" | "bao" | "xien" | "de" | "cham";

const PICK_BUCKET_LABELS: Record<PickBucket, string> = {
  btl: "BTL lô",
  bao: "Bao lô",
  xien: "Xiên 2",
  de: "Đề",
  cham: "Chạm đề",
};

let currentPickWhoMap = new Map<string, string[]>();
let lastRecommendationsForCopy: RecommendationsResponse | null = null;
let recoExpertSort: RecoExpertSortMode = "effective";
let recoScoringMode: RecoScoringMode = "blend";

function sortLiveExperts(experts: LiveExpertRow[]): LiveExpertRow[] {
  const rows = [...experts];
  if (recoExpertSort === "performance") {
    rows.sort((a, b) => {
      const ar = a.performance?.rate_pct ?? -1;
      const br = b.performance?.rate_pct ?? -1;
      if (br !== ar) return br - ar;
      const at = a.performance?.total ?? 0;
      const bt = b.performance?.total ?? 0;
      if (bt !== at) return bt - at;
      return a.user.localeCompare(b.user);
    });
  } else if (recoExpertSort === "effective") {
    rows.sort((a, b) => {
      const ar = a.effective_weight ?? a.weight;
      const br = b.effective_weight ?? b.weight;
      if (br !== ar) return br - ar;
      return a.user.localeCompare(b.user);
    });
  } else {
    rows.sort((a, b) => b.weight - a.weight || a.user.localeCompare(b.user));
  }
  return rows;
}

function updateRecoExpertSortUi(): void {
  $("btn-sort-experts-weight").classList.toggle("active", recoExpertSort === "weight");
  $("btn-sort-experts-perf").classList.toggle("active", recoExpertSort === "performance");
  $("btn-sort-experts-effective").classList.toggle("active", recoExpertSort === "effective");
}

function updateRecoScoringModeUi(): void {
  $("btn-scoring-blend").classList.toggle("active", recoScoringMode === "blend");
  $("btn-scoring-weight").classList.toggle("active", recoScoringMode === "weight");
  $("btn-scoring-measured").classList.toggle("active", recoScoringMode === "measured");
}

function renderLiveExpertsTable(experts: LiveExpertRow[]): void {
  const tbody = $("reco-experts-rows");
  if (!experts.length) {
    tbody.innerHTML = "<tr><td colspan='8' class='muted'>Chưa có cao thủ chốt (poll + sync API)</td></tr>";
    return;
  }
  const showEff = recoScoringMode !== "weight";
  tbody.innerHTML = sortLiveExperts(experts)
    .slice(0, 20)
    .map((e) => {
      const tag = fmtForumTag(e.forum);
      const label = PICK_LABELS[e.pick_type] || e.pick_type;
      const nums =
        e.pick_type === "std_de"
          ? (e.numbers || []).join(" / ")
          : (e.numbers || []).join(", ");
      const topic = e.thread_url
        ? `<a class="muted" href="${e.thread_url}" target="_blank" rel="noreferrer">threads/${(e.thread_id || "").slice(0, 18)}${(e.thread_id || "").length > 18 ? "…" : ""}</a>`
        : "—";
      const eff = e.effective_weight ?? e.weight;
      const effCell = showEff ? `<td>${eff.toFixed(2)}</td>` : "<td class='muted'>—</td>";
      return `<tr data-user="${e.user}" data-forum="${e.forum || ""}">
        <td><strong>${e.user}</strong></td>
        <td>${tag ? `<span class="forum-tag forum-tag-${tag.toLowerCase()}">${tag}</span>` : "—"}</td>
        <td>${topic}</td>
        <td>${label}</td>
        <td class="nums">${nums}</td>
        <td>${formatPerformance(e.performance)}</td>
        <td>${e.weight}</td>
        ${effCell}
      </tr>`;
    })
    .join("");
}

function joinOrDash(items: string[], sep = ", "): string {
  return items.length ? items.join(sep) : "—";
}

async function copyTextToClipboard(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
  }
}

async function flashCopyButton(btn: HTMLButtonElement): Promise<void> {
  const prev = btn.textContent || "Copy";
  btn.textContent = "Đã copy";
  btn.classList.add("copied");
  await new Promise((r) => setTimeout(r, 900));
  btn.textContent = prev;
  btn.classList.remove("copied");
}

function formatExpertPanelCopy(data: RecommendationsResponse, targetDate: string): string {
  const picks = data.picks;
  const cham = [
    ...new Set((data.de_cham_leaders || []).flatMap((c) => c.cham.map((d) => String(d).trim()))),
  ];
  const lines = [
    `Theo cao thủ (trọng số) · ${formatTargetDateLabel(targetDate)}`,
    `BTL lô: ${picks.btl_lo || "—"}`,
    `Bao lô 9: ${joinOrDash(picks.bao_lo_9 || [])}`,
    `Xiên 2: ${joinOrDash(picks.xien_2 || [], " / ")}`,
    `Đề top 4: ${joinOrDash(picks.de_top_4 || [])}`,
    `Chạm đề: ${joinOrDash(cham)}`,
  ];
  return lines.join("\n");
}

function formatConsensusPanelCopy(data: RecommendationsResponse, targetDate: string): string {
  const consensus = data.consensus;
  if (!consensus?.picks) {
    return `Theo đồng thuận (số người chốt) · ${formatTargetDateLabel(targetDate)}\nChưa có dữ liệu`;
  }
  const voteMap = buildVoteMap(consensus.loto_top10 || []);
  const bao = (consensus.picks.bao_lo_9 || []).map((n) => {
    const v = voteMap.get(n);
    return v && v >= 2 ? `${n}×${v}` : n;
  });
  const cham = (consensus.de_cham || []).map((c) => {
    const votes = c.votes ?? 0;
    return votes >= 2 ? `${c.cham}×${votes}` : String(c.cham);
  });
  const lines = [
    `Theo đồng thuận (số người chốt) · ${formatTargetDateLabel(targetDate)}`,
    `BTL lô: ${consensus.picks.btl_lo || "—"}`,
    `Bao lô 9: ${joinOrDash(bao)}`,
    `Xiên 2: ${joinOrDash(consensus.picks.xien_2 || [], " / ")}`,
    `Đề top 4: ${joinOrDash(consensus.picks.de_top_4 || [])}`,
    `Chạm đề: ${joinOrDash(cham)}`,
  ];
  return lines.join("\n");
}

function setupRecoPanelCopyHandlers(): void {
  $("btn-copy-reco-expert").addEventListener("click", async () => {
    const btn = $("btn-copy-reco-expert") as HTMLButtonElement;
    const data = lastRecommendationsForCopy;
    if (!data) return;
    const target = data.target_date || $("reco-target-date").textContent || "";
    await copyTextToClipboard(formatExpertPanelCopy(data, target));
    await flashCopyButton(btn);
  });

  $("btn-copy-reco-consensus").addEventListener("click", async () => {
    const btn = $("btn-copy-reco-consensus") as HTMLButtonElement;
    const data = lastRecommendationsForCopy;
    if (!data) return;
    const target = data.target_date || $("reco-target-date").textContent || "";
    await copyTextToClipboard(formatConsensusPanelCopy(data, target));
    await flashCopyButton(btn);
  });
}

function normToken(bucket: PickBucket, token: string): string {
  const t = (token || "").trim();
  if (!t) return t;
  if (bucket === "xien") return t; // e.g. "13-77"
  if (bucket === "cham") return t.replace(/[^\d]/g, "").slice(0, 1); // digit
  // btl/bao/de: normalize 1-2 digit numbers → 2 digits
  const m = t.match(/^\d{1,2}$/);
  if (m) return t.padStart(2, "0");
  return t;
}

function pickBucket(pickType: string): PickBucket | null {
  const t = pickType.toLowerCase();
  if (t === "btl" || t.includes("btl")) return "btl";
  if (t.includes("bao")) return "bao";
  if (t.includes("xien")) return "xien";
  // de_* / btd / btd_dau cũng coi là "de" cho tooltip basic
  if (t.includes("de") || t.includes("btd")) return "de";
  if (t.includes("cham")) return "cham";
  return null;
}

function buildWhoMap(data: RecommendationsResponse): Map<string, string[]> {
  const map = new Map<string, Set<string>>();

  const add = (bucket: PickBucket, token: string, user: string) => {
    const key = `${bucket}:${normToken(bucket, token)}`;
    const set = map.get(key) || new Set<string>();
    set.add(user);
    map.set(key, set);
  };

  for (const e of data.live_experts || []) {
    const b = pickBucket(e.pick_type);
    if (!b) continue;
    for (const raw of e.numbers || []) {
      const token = String(raw).trim();
      if (!token) continue;
      add(b, token, e.user);
    }
  }

  // Consensus có users rõ cho loto_top10 → dùng bổ sung cho tooltip
  for (const row of data.consensus?.loto_top10 || []) {
    for (const u of row.users || []) {
      add("btl", row.loto, u);
      add("bao", row.loto, u);
    }
  }

  // Chạm leaders
  for (const c of data.de_cham_leaders || []) {
    for (const raw of c.cham || []) add("cham", String(raw).trim(), c.user);
  }
  for (const c of data.consensus?.de_cham || []) {
    for (const u of c.users || []) add("cham", String(c.cham).trim(), u);
  }

  const out = new Map<string, string[]>();
  for (const [k, v] of map.entries()) out.set(k, [...v].sort((a, b) => a.localeCompare(b)));
  return out;
}

function renderPickChip(
  bucket: PickBucket,
  token: string,
  label: string,
  who: Map<string, string[]>,
  extraClass = "",
): string {
  const norm = normToken(bucket, token);
  const users = who.get(`${bucket}:${norm}`) || [];
  const hint = users.length ? users.join(", ") : "Chưa rõ ai chốt";
  const hasWho = users.length > 0 ? "has-who" : "";
  const cls = ["pick-chip", hasWho, extraClass].filter(Boolean).join(" ");
  return `<button type="button" class="${cls}" data-bucket="${bucket}" data-token="${norm}" data-label="${label.replace(/"/g, "&quot;")}" title="${hint.replace(/"/g, "&quot;")}">${label}</button>`;
}

function renderTokensWithWho(
  bucket: PickBucket,
  tokens: string[],
  who: Map<string, string[]>,
  opts: { diff?: (token: string) => string | null; label?: (token: string) => string } = {},
): string {
  if (!tokens.length) return "—";
  return tokens
    .map((t) => {
      const token = String(t).trim();
      const label = opts.label ? opts.label(token) : token;
      const diffCls = opts.diff?.(token) ? "nums-diff" : "";
      return renderPickChip(bucket, token, label, who, diffCls);
    })
    .join(", ");
}

function renderXienWithWho(tokens: string[], who: Map<string, string[]>): string {
  if (!tokens.length) return "—";
  return tokens
    .map((pair) => {
      const token = String(pair).trim();
      return renderPickChip("xien", token, token, who);
    })
    .join(" / ");
}

function renderChamWithWho(
  who: Map<string, string[]>,
  digits: string[],
  labelFn?: (d: string) => string,
): string {
  if (!digits.length) return "—";
  return digits
    .map((d) => {
      const token = String(d).trim();
      const label = labelFn ? labelFn(token) : token;
      return renderPickChip("cham", token, label, who);
    })
    .join(", ");
}

function showPickWhoPopup(bucket: PickBucket, token: string, label: string, overrideUsers?: string[]): void {
  const users = overrideUsers || currentPickWhoMap.get(`${bucket}:${token}`) || [];
  const popup = $("pick-who-popup");
  $("pick-who-title").textContent = label || token;
  $("pick-who-sub").textContent = PICK_BUCKET_LABELS[bucket] || bucket;
  const list = $("pick-who-list");
  if (!users.length) {
    list.innerHTML = "<li class='muted'>Chưa rõ ai chốt</li>";
  } else {
    list.innerHTML = users.map((u) => `<li><strong>${u}</strong></li>`).join("");
  }
  popup.classList.remove("hidden");
  popup.hidden = false;
}

function closePickWhoPopup(): void {
  const popup = $("pick-who-popup");
  popup.classList.add("hidden");
  popup.hidden = true;
}

function setupPickWhoPopup(): void {
  const popup = $("pick-who-popup");
  popup.querySelector(".pick-who-backdrop")?.addEventListener("click", closePickWhoPopup);
  popup.querySelector(".pick-who-close")?.addEventListener("click", closePickWhoPopup);

  const panels = [$("panel-reco"), $("panel-score")];
  for (const panel of panels) {
    panel.addEventListener("click", (ev) => {
      const chip = (ev.target as HTMLElement).closest(".pick-chip") as HTMLButtonElement | null;
      if (!chip) return;
      // Score tab chip — khác format, xử lý riêng
      const scoreNum = chip.dataset.scoreNum;
      if (scoreNum) {
        const user = chip.dataset.scoreUser || "";
        showPickWhoPopup("de", scoreNum, scoreNum, [user]);
        ev.preventDefault();
        ev.stopPropagation();
        return;
      }
      const bucket = chip.dataset.bucket as PickBucket;
      const token = chip.dataset.token || "";
      const label = chip.dataset.label || token;
      if (!bucket || !token) return;
      showPickWhoPopup(bucket, token, label);
      ev.preventDefault();
      ev.stopPropagation();
    });
  }

  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && !popup.hidden) closePickWhoPopup();
  });
}

function setupRecoPanelCollapses(): void {
  const specs: Array<{ toggleId: string; targetId: string }> = [
    { toggleId: "toggle-reco-de-by-expert", targetId: "reco-de-by-expert" },
    { toggleId: "toggle-reco-dan-board", targetId: "reco-dan-board" },
    { toggleId: "toggle-reco-dan-filter", targetId: "reco-dan-filter" },
  ];

  for (const { toggleId, targetId } of specs) {
    const btn = $(toggleId) as HTMLButtonElement;
    const target = $(targetId) as HTMLElement;
    if (!btn || !target) continue;

    const sync = (): void => {
      const hidden = target.hidden || target.classList.contains("hidden");
      target.hidden = hidden;
      target.classList.toggle("hidden", hidden);
      btn.textContent = hidden ? "▸" : "▾";
      btn.setAttribute("aria-expanded", String(!hidden));
    };

    // Normalize initial state.
    sync();

    btn.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      target.hidden = !target.hidden;
      target.classList.toggle("hidden", target.hidden);
      sync();
    });
  }
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

/**
 * Clear all recommendation pick fields — used when API returns data for wrong target_date
 */
function clearRecoPicks(): void {
  $("reco-btl").textContent = "—";
  $("reco-bao").textContent = "—";
  $("reco-xien").textContent = "—";
  $("reco-de").textContent = "—";
  $("reco-cham").textContent = "—";
  $("reco-consensus-btl").textContent = "—";
  $("reco-consensus-bao").textContent = "—";
  $("reco-consensus-xien").textContent = "—";
  $("reco-consensus-de").textContent = "—";
  $("reco-consensus-cham").textContent = "—";
  $("reco-consensus-hint").classList.add("hidden");
  $("reco-consensus-hint").hidden = true;
  const tbody = $("reco-experts-rows");
  tbody.innerHTML = "<tr><td colspan='7' class='muted'>Chưa có dữ liệu — API trả ngày cũ, cần poll forum cho ngày mới</td></tr>";
  lastRecommendationsForCopy = null;
}

function renderRecommendations(
  data: RecommendationsResponse,
  expectedTarget: string,
  afterCutoff: boolean,
): void {
  $("reco-target-date").textContent = formatTargetDateLabel(data.target_date || expectedTarget);
  $("reco-expert-count").textContent = String(data.expert_count ?? data.live_experts.length);

  const hint = $("reco-freshness-hint");
  if (data.target_date && data.target_date !== expectedTarget) {
    hint.textContent = `API trả ngày ${formatTargetDateLabel(data.target_date)} — khác ngày quay hiện tại ${formatTargetDateLabel(expectedTarget)}. Bấm Tải đề xuất lại.`;
    hint.classList.remove("hidden", "ok");
    hint.hidden = false;
  } else if (afterCutoff) {
    hint.textContent = `Đề xuất cho ngày quay ${formatTargetDateLabel(expectedTarget)} — sau 18:30 dùng pick mới (thảo luận + chăn nuôi).`;
    hint.classList.remove("hidden");
    hint.classList.add("ok");
    hint.hidden = false;
  } else {
    hint.classList.add("hidden");
    hint.hidden = true;
  }

  const voteMap = buildVoteMap(data.consensus?.loto_top10 || []);
  const expertBao = data.picks.bao_lo_9;
  const consensusBao = data.consensus?.picks?.bao_lo_9 || [];
  const consensusSet = new Set(consensusBao);
  const who = buildWhoMap(data);
  currentPickWhoMap = who;

  const btl = data.picks.btl_lo ? [data.picks.btl_lo] : [];
  $("reco-btl").innerHTML = renderTokensWithWho("btl", btl, who);
  $("reco-bao").innerHTML = renderTokensWithWho("bao", expertBao, who);

  $("reco-xien").innerHTML = renderXienWithWho(data.picks.xien_2 || [], who);

  $("reco-de").innerHTML = renderTokensWithWho("de", data.picks.de_top_4, who);

  const chamDigits = [
    ...new Set((data.de_cham_leaders || []).flatMap((c) => c.cham.map((d) => String(d).trim()))),
  ];
  $("reco-cham").innerHTML = renderChamWithWho(who, chamDigits);

  const consensus = data.consensus;
  if (consensus?.picks) {
    const cbtl = consensus.picks.btl_lo ? [consensus.picks.btl_lo] : [];
    $("reco-consensus-btl").innerHTML = renderTokensWithWho("btl", cbtl, who);
    $("reco-consensus-bao").innerHTML = renderTokensWithWho("bao", consensusBao, who, {
      label: (n) => {
        const v = voteMap.get(n);
        return v && v >= 2 ? `${n}×${v}` : n;
      },
    });

    const cxien = consensus.picks.xien_2 || [];
    $("reco-consensus-xien").innerHTML = renderXienWithWho(cxien, who);

    $("reco-consensus-de").innerHTML = renderTokensWithWho("de", consensus.picks.de_top_4, who);
    const chamDigits = (consensus.de_cham || []).map((c) => String(c.cham).trim());
    $("reco-consensus-cham").innerHTML = renderChamWithWho(
      who,
      chamDigits,
      (d) => {
        const row = (consensus.de_cham || []).find((c) => String(c.cham) === d);
        const votes = row?.votes ?? 0;
        return votes >= 2 ? `${d}×${votes}` : d;
      },
    );
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
    $("reco-bao").innerHTML = renderTokensWithWho("bao", expertBao, who, {
      diff: (n) => (consensusSet.has(n) ? null : "Chỉ panel trọng số"),
    });
    $("reco-consensus-bao").innerHTML = renderTokensWithWho("bao", consensusBao, who, {
      diff: (n) => (expertBao.includes(n) ? null : "Chỉ panel đồng thuận"),
      label: (n) => {
        const v = voteMap.get(n);
        return v && v >= 2 ? `${n}×${v}` : n;
      },
    });
  }

  renderDeByExpert(data);
  renderDanBoard(data.dan_board || []);

  const periodLabel = data.scoring_period_label || data.performance_period_label || "90 ngày gần nhất";
  const modeLabel = data.scoring_mode_label || recoScoringMode;
  $("reco-experts-legend").textContent =
    `W = trọng số thủ công · Hiệu suất = hit/total (${periodLabel}) · Đề xuất số: ${modeLabel} · * mẫu nhỏ`;

  renderLiveExpertsTable(data.live_experts || []);

  renderTopLotoExperts(data.live_experts || []);

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
  lastRecommendationsForCopy = data;
}

function renderCandidateTable(
  tbodyId: string,
  rows: { loto: string; score: number; filters_matched: number }[],
  emptyMsg: string,
): void {
  const tbody = $(tbodyId);
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="4" class="muted">${emptyMsg}</td></tr>`;
    return;
  }
  tbody.innerHTML = rows
    .map(
      (r, i) =>
        `<tr title="${(r as { reasons?: string[] }).reasons?.[0] || ""}">
          <td>${i + 1}</td>
          <td><strong>${r.loto}</strong></td>
          <td>${r.score.toFixed(2)}</td>
          <td>${r.filters_matched}</td>
        </tr>`,
    )
    .join("");
}

function pickLoto(item: { loto: string } | string): string {
  return typeof item === "string" ? item : item.loto;
}

function daysBetweenIso(a: string, b: string): number {
  const ta = Date.parse(`${a}T12:00:00Z`);
  const tb = Date.parse(`${b}T12:00:00Z`);
  if (Number.isNaN(ta) || Number.isNaN(tb)) return 0;
  return Math.round(Math.abs(tb - ta) / 86_400_000);
}

function renderEngine(data: EngineBundle, settings: Awaited<ReturnType<typeof getSettings>>): void {
  const loto = data.stats_loto;
  const de = data.stats_de;
  const ix = data.intersection;
  const asOf = data.as_of_date || loto.as_of_date || ix.as_of_date || "—";

  $("engine-target-date").textContent = data.target_date;
  $("engine-as-of").textContent = asOf;
  $("engine-db-draws").textContent = data.analytics?.mb_draws
    ? `${data.analytics.mb_draws} (${data.analytics.oldest || "?"} → ${data.analytics.newest || "?"})`
    : "—";
  $("engine-api-base").textContent = data.api_base.replace(/^https?:\/\//, "");

  const stale = $("engine-stale-warn");
  const calendarToday = getCalendarDate(new Date(), settings.timezone);
  const newest = data.analytics?.newest || asOf;
  const gap = newest !== "—" ? daysBetweenIso(newest, calendarToday) : 0;
  if (gap > 1) {
    stale.textContent =
      `KQXS trong DB mới đến ${formatTargetDateLabel(newest)} (thiếu ${gap} ngày). ` +
      "Chạy import KQXS trên server rồi bấm Tải engine lại.";
    stale.classList.remove("hidden");
  } else {
    stale.classList.add("hidden");
  }

  const disclaimer = $("engine-disclaimer");
  const disc = loto.disclaimer || de.disclaimer;
  if (disc) {
    disclaimer.textContent = disc;
    disclaimer.classList.remove("hidden");
  } else {
    disclaimer.classList.add("hidden");
  }

  renderCandidateTable("engine-loto-rows", loto.candidates || [], "Chưa có candidate lô");
  renderCandidateTable("engine-de-rows", de.candidates || [], "Chưa có candidate đề");

  const ctx = loto.context as { weekday_vi?: string; yesterday_db?: string } | undefined;
  const yDb = ix.yesterday_db || ctx?.yesterday_db || "—";
  $("engine-intersection-meta").textContent =
    `ĐB hôm qua: ${yDb}` +
    (ctx?.weekday_vi ? ` · ${ctx.weekday_vi}` : "") +
    (ix.strategy ? ` · ${ix.strategy}` : "");

  const cfTop = (ix.cf_candidates || []).slice(0, 8).map((c) => c.loto).join(", ");
  $("engine-cf-top").textContent = cfTop || "—";

  const rbkTop = (ix.rbk_candidates || []).slice(0, 8).map(pickLoto).join(", ");
  $("engine-rbk-top").textContent = rbkTop || "—";

  const finals = (ix.final_picks?.length ? ix.final_picks : ix.intersection) || [];
  $("engine-final-picks").textContent =
    finals.length ? finals.map(pickLoto).join(", ") : "— (chưa giao)";

  const predBody = $("engine-predict-rows");
  const preds = data.predictions?.predictions || [];
  if (!preds.length) {
    predBody.innerHTML =
      "<tr><td colspan='3' class='muted'>Prediction engine không khả dụng</td></tr>";
  } else {
    predBody.innerHTML = preds
      .map(
        (p) =>
          `<tr><td>${p.rank}</td><td><strong>${p.value}</strong></td><td>${p.score.toFixed(3)}</td></tr>`,
      )
      .join("");
  }

  $("engine-error").classList.add("hidden");
}

async function loadEngine(): Promise<void> {
  if (engineLoading) return;

  $("engine-error").classList.add("hidden");
  setEngineLoading(true, "Kết nối Stats Engine…");

  try {
    const settings = await ensureApiOnline(await getSettings());
    const data = await fetchEngineBundle(settings);
    renderEngine(data, settings);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    const err = $("engine-error");
    err.textContent = msg;
    err.classList.remove("hidden");
  } finally {
    setEngineLoading(false);
  }
}

async function loadRecommendations(options: { forcePoll?: boolean } = {}): Promise<void> {
  if (recoLoading) return;

  const now = new Date();
  lastRecoTarget = getTargetDate(now, (await getSettings()).timezone);

  $("reco-error").classList.add("hidden");
  startRecoLoadingAnimation();

  try {
    const settings = await ensureApiOnline(await getSettings());
    const target = getTargetDate(now, settings.timezone);
    lastRecoTarget = target;
    const afterCutoff = isAfterResultCutoff(now, settings.timezone);
    const runtime = await getRuntimeStatus();
    const rolledOver = Boolean(runtime.target_date && runtime.target_date !== target);
    let session = await getSession(target);
    const shouldPoll =
      options.forcePoll || rolledOver || needsPollForTarget(target, runtime, session, afterCutoff);

    $("reco-loading-text").textContent = "Lấy pick cao thủ…";
    let data = await fetchRecommendationsAndSyncUrl(target, settings, recoScoringMode);
    const dataIsFresh = data.target_date === target;
    const hasApiData = Boolean(data.has_forum_session || data.expert_count > 0);

    // Only render if API returned data for the correct target date
    if (dataIsFresh && hasApiData) {
      renderRecommendations(data, target, afterCutoff);
    } else if (!dataIsFresh) {
      // API trả data cũ — clear UI thay vì render data sai ngày
      clearRecoPicks();
      const hint = $("reco-freshness-hint");
      hint.textContent = `API đang trả dữ liệu ngày ${formatTargetDateLabel(data.target_date)} — cần poll forum cho ngày mới ${formatTargetDateLabel(target)}.`;
      hint.classList.remove("hidden", "ok");
      hint.hidden = false;
    }

    if (shouldPoll) {
      $("reco-loading-text").textContent = "Đang poll forum…";
      try {
        await pollNowWithTimeout();
        session = await getSession(target);
      } catch {
        if (!hasApiData && dataIsFresh) {
          const hint = $("reco-freshness-hint");
          hint.textContent =
            "Poll forum chậm hoặc lỗi — thử Poll ngay ở tab Thu thập, rồi Tải đề xuất lại.";
          hint.classList.remove("hidden", "ok");
          hint.hidden = false;
        }
      }
    }

    if (session && (shouldPoll || options.forcePoll)) {
      $("reco-loading-text").textContent = "Đang sync session lên API…";
      await syncSessionOptional(session, true);
      data = await fetchRecommendationsAndSyncUrl(target, settings);
    }

    // Re-check after poll+sync
    const dataIsFresh2 = data.target_date === target;
    if (dataIsFresh2 && (data.has_forum_session || data.expert_count > 0)) {
      renderRecommendations(data, target, afterCutoff);
    } else if (!dataIsFresh2) {
      // Still no fresh data — show clear message, không render data cũ
      clearRecoPicks();
      throw new Error(
        `Chưa có dữ liệu cho ngày ${formatTargetDateLabel(target)} — sau 18:30 cao thủ chốt đề mới, poll forum trước.`,
      );
    }

    if (!data.has_forum_session && data.expert_count === 0) {
      // Only throw if data is for correct target (stale data already handled above)
      throw new Error(
        "Chưa có dữ liệu cao thủ — poll forum trước (tab Thu thập), rồi bấm Tải đề xuất",
      );
    }

    // Check if API returned data for a different target date (after re-fetch)
    if (data.target_date && data.target_date !== target) {
      const hint = $("reco-freshness-hint");
      hint.textContent = `API trả ngày ${formatTargetDateLabel(data.target_date)} — khác ngày quay hiện tại ${formatTargetDateLabel(target)}. Bấm Tải đề xuất lại.`;
      hint.classList.remove("hidden", "ok");
      hint.hidden = false;
    }
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
  const now = new Date();
  const target = getTargetDate(now, settings.timezone);
  const { window_start, window_end } = getCollectWindow(target, settings.timezone);
  const afterCutoff = isAfterResultCutoff(now, settings.timezone);

  const badge = $("status-badge");
  badge.textContent = collectStatusLabel(runtime.collect_status);
  badge.className = `badge ${badgeClass(runtime.collect_status)}`;

  $("target-date").textContent = target;
  $("window-range").textContent = afterCutoff
    ? `${window_start} → ${window_end} · sau 18:30 → ngày quay mới`
    : `${window_start} → ${window_end}`;
  $("post-count").textContent = String(runtime.post_count);
  $("new-posts").textContent = String(runtime.new_posts_last_poll);
  $("last-poll").textContent = runtime.last_poll_at
    ? new Date(runtime.last_poll_at).toLocaleString("vi-VN")
    : "—";
  $("last-poll-status").textContent = runtime.last_poll_status
    ? pollStatusLabel(runtime.last_poll_status)
    : "—";

  const session = await getSession(target);
  const backfillEl = $("backfill-status");
  if (session?.threads) {
    const dailyKeys = ["thao_luan", "mo_bat"] as const;
    const lines: string[] = [];
    for (const dk of dailyKeys) {
      const st = session.threads[dk];
      if (!st) continue;
      const low = st.lowest_page_fetched ?? st.last_page_fetched ?? "?";
      const high = st.last_page_fetched ?? "?";
      if (st.backfill_complete) {
        lines.push(`${dk === "thao_luan" ? "TL" : "MB"}: ✓`);
      } else {
        lines.push(`${dk === "thao_luan" ? "TL" : "MB"}: ${low}/${high} ↓`);
      }
    }
    backfillEl.textContent = lines.length ? lines.join(" · ") : "—";
  } else {
    backfillEl.textContent = "—";
  }

  $("auth-status-short").textContent =
    runtime.auth_status === "logged_in"
      ? `${authLabel(runtime.auth_status)} · ${auth.username || "—"}`
      : authLabel(runtime.auth_status);
  const authCard = $("auth-card");
  const loggedIn = runtime.auth_status === "logged_in";
  authCard.classList.toggle("logged-in", loggedIn);
  const loginUrl = auth.login_url || "https://forumketqua.net/login/";
  const hint = $("auth-logged-hint");
  if (loggedIn) {
    hint.textContent = `Đã đăng nhập: ${auth.username || "—"} · ${loginUrl}`;
    hint.classList.remove("hidden");
  } else {
    hint.classList.add("hidden");
  }
  $("cfg-login-url").textContent = loginUrl;
  $("cfg-username").textContent = auth.username || "—";
  $("cfg-password").textContent = maskPassword(auth.password);
  $("cfg-api-url").textContent = settings.api_base_url;
  const apiStatus = $("cfg-api-status");
  const apiPing = await resolveWorkingApiBase(settings);
  if (apiPing.online) {
    apiStatus.textContent = "Online";
    apiStatus.className = "api-status online";
    if (apiPing.base) $("cfg-api-url").textContent = apiPing.base;
  } else {
    apiStatus.textContent = apiPing.error
      ? `Offline (${apiPing.error})`
      : "Offline — chạy APP_PORT=18715 python run.py";
    apiStatus.className = "api-status offline";
  }
  $("cfg-auto-sync").textContent = settings.auto_sync ? "Bật" : "Tắt";
  $("cfg-poll-active").textContent = `${settings.poll_interval_active_min} phút`;

  const err = $("error");
  if (runtime.last_error) {
    err.textContent = runtime.last_error;
    err.classList.remove("hidden");
  } else {
    err.classList.add("hidden");
  }

  if ($("tab-reco").classList.contains("active") && target !== lastRecoTarget && !recoLoading) {
    void loadRecommendations();
  }
}

$("tab-collect").addEventListener("click", () => setTab("collect"));
$("tab-reco").addEventListener("click", () => setTab("reco"));
$("tab-engine").addEventListener("click", () => setTab("engine"));
$("tab-score").addEventListener("click", () => setTab("score"));
$("btn-refresh-reco").addEventListener("click", () => loadRecommendations({ forcePoll: true }));
$("btn-sort-experts-weight").addEventListener("click", async () => {
  recoExpertSort = "weight";
  await saveRecoExpertSort(recoExpertSort);
  updateRecoExpertSortUi();
  if (lastRecommendationsForCopy) renderLiveExpertsTable(lastRecommendationsForCopy.live_experts || []);
});
$("btn-sort-experts-perf").addEventListener("click", async () => {
  recoExpertSort = "performance";
  await saveRecoExpertSort(recoExpertSort);
  updateRecoExpertSortUi();
  if (lastRecommendationsForCopy) renderLiveExpertsTable(lastRecommendationsForCopy.live_experts || []);
});
$("btn-sort-experts-effective").addEventListener("click", async () => {
  recoExpertSort = "effective";
  await saveRecoExpertSort(recoExpertSort);
  updateRecoExpertSortUi();
  if (lastRecommendationsForCopy) renderLiveExpertsTable(lastRecommendationsForCopy.live_experts || []);
});
async function setRecoScoringMode(mode: RecoScoringMode): Promise<void> {
  recoScoringMode = mode;
  await saveRecoScoringMode(mode);
  updateRecoScoringModeUi();
  await loadRecommendations();
}
$("btn-scoring-blend").addEventListener("click", () => void setRecoScoringMode("blend"));
$("btn-scoring-weight").addEventListener("click", () => void setRecoScoringMode("weight"));
$("btn-scoring-measured").addEventListener("click", () => void setRecoScoringMode("measured"));
$("btn-refresh-engine").addEventListener("click", () => loadEngine());
$("btn-refresh-score").addEventListener("click", () => loadScore(false));
$("btn-run-score").addEventListener("click", () => loadScore(true));

setupDanCopyHandlers();
setupRecoPanelCopyHandlers();
setupDeJumpHandlers();
setupPickWhoPopup();
setupRecoPanelCollapses();

$("btn-poll").addEventListener("click", async () => {
  const btn = $("btn-poll");
  btn.textContent = "Đang poll…";
  try {
    const result = (await send("POLL_NOW")) as { status?: string; added?: number; error?: string };
    if (result?.error) {
      $("last-poll-status").textContent = result.error;
    } else if (result?.status) {
      const label = pollStatusLabel(result.status);
      const extra = result.added ? ` (+${result.added})` : "";
      $("last-poll-status").textContent = `${label}${extra}`;
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    $("last-poll-status").textContent = msg;
  }
  await refreshUi();
  btn.textContent = "Poll ngay";
});

$("btn-login").addEventListener("click", async () => {
  $("btn-login").textContent = "…";
  await send("LOGIN");
  await refreshUi();
  $("btn-login").textContent = "Đăng nhập lại";
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
  settingsPanel.classList.toggle("collapsed", !open);
  toggleSettingsBtn.setAttribute("aria-expanded", String(open));
}

toggleSettingsBtn.addEventListener("click", () => {
  setSettingsOpen(settingsPanel.classList.contains("collapsed"));
});

async function initPopup(): Promise<void> {
  await ensureConfigSeeded();
  recoExpertSort = await getRecoExpertSort();
  recoScoringMode = await getRecoScoringMode();
  updateRecoExpertSortUi();
  updateRecoScoringModeUi();
  setSettingsOpen(true);
  await refreshUi();

  // Auto-expand popup to full content height (override Chrome's default ~600px max-height limit)
  // Chrome extension popup has a built-in max-height ~600px that cannot be overridden by CSS.
  // Dynamically setting body.minHeight forces Chrome to expand the popup window.
  requestAnimationFrame(() => {
    const html = document.documentElement;
    const body = document.body;
    const totalHeight = Math.max(html.scrollHeight, body.scrollHeight);
    if (totalHeight > 600) {
      body.style.minHeight = `${totalHeight}px`;
      html.style.height = `${totalHeight}px`;
    }
  });
}

void initPopup();
setInterval(refreshUi, 5000);
