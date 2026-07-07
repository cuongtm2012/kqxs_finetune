import type { CollectSession, DiscoveredThread, ForumKey, ThreadState } from "../types/forum.js";
import {
  getCollectWindow,
  getNextRolloverMs,
  getTargetDate,
  getWindowBoundsMs,
  isInCollectWindow,
  isPastFinalizeGrace,
  shouldFinalize,
} from "./date-window.js";
import { clearForumHtmlCache, ensureLoggedIn, fetchForumHtml } from "./forum-auth.js";
import { ensureForumTab } from "./forum-tabs.js";
import {
  extractPostsFromHtml,
  getLastPageFromHtml,
  toForumPosts,
} from "./forum-html-parser.js";
import { discoverAllThreads } from "./thread-discovery.js";
import { buildSummary, emptySession, mergePosts } from "./summary.js";
import { syncSessionToApi } from "./api-client.js";
import {
  getSession,
  getSettings,
  getRuntimeStatus,
  patchRuntimeStatus,
  pruneOldSessions,
  saveSession,
} from "./storage.js";
import type { ExtensionSettings } from "../types/forum.js";

const DAILY_FORUMS = new Set<ForumKey>(["mo_bat", "thao_luan"]);
const THAO_LUAN_DE_TYPES = new Set([
  "btd",
  "btd_de",
  "std_de",
  "de_cham",
  "de_dau",
  "de_tong",
  "btd_dau",
  "de_list",
]);

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function thaoLuanPostCount(session: CollectSession): number {
  return Object.values(session.posts || {}).filter((p) => p.forum === "thao_luan").length;
}

function thaoLuanHasDeSignals(session: CollectSession): boolean {
  for (const p of Object.values(session.posts || {})) {
    if (p.forum !== "thao_luan") continue;
    for (const k of Object.keys(p.picks || {})) {
      if (THAO_LUAN_DE_TYPES.has(k)) return true;
    }
  }
  return false;
}

async function finalizeCollectSession(
  session: CollectSession,
  settings: ExtensionSettings,
  coverageWarning = false,
): Promise<void> {
  if (session.finalized_at) return;
  session.summary = buildSummary(session, settings);
  session.finalized_at = new Date().toISOString();
  session.coverage_warning = coverageWarning;
  await saveSession(session);
  if (settings.auto_sync) {
    await syncSessionToApi(session);
  }
}

function threadStorageKey(forum: ForumKey, slug: string): string {
  return forum === "chan_nuoi" ? `chan_nuoi:${slug}` : forum;
}

const CRAWL_COOLDOWN_MS = 5 * 60 * 1000;

function needsBackfill(state: ThreadState): boolean {
  return !state.backfill_complete && (state.lowest_page_fetched ?? 1) > 1;
}

function dailyThreadsNeedBackfill(
  session: CollectSession,
  threads: DiscoveredThread[],
): boolean {
  for (const thread of threads) {
    if (!DAILY_FORUMS.has(thread.forum)) continue;
    const key = threadStorageKey(thread.forum, thread.slug);
    const state = session.threads[key];
    if (!state || needsBackfill(state)) return true;
  }
  return false;
}

function canFinalizeSession(
  session: CollectSession,
  threads: DiscoveredThread[],
  now: Date,
  targetDate: string,
  timeZone: string,
): { allow: boolean; coverageWarning: boolean } {
  if (!shouldFinalize(now, targetDate, timeZone)) {
    return { allow: false, coverageWarning: false };
  }
  if (!dailyThreadsNeedBackfill(session, threads)) {
    return { allow: true, coverageWarning: false };
  }
  if (isPastFinalizeGrace(now, targetDate, timeZone)) {
    return { allow: true, coverageWarning: true };
  }
  return { allow: false, coverageWarning: false };
}

async function resolveThreads(
  targetDate: string,
  session: CollectSession,
  patterns: string[],
  force: boolean,
): Promise<DiscoveredThread[]> {
  if (!force && session.discovered_threads?.length) {
    return session.discovered_threads;
  }
  // Force poll should be robust against transient listing fetch / tab injection races.
  // Retry discovery a few times; prefer having at least the Thảo luận thread.
  let last: DiscoveredThread[] = [];
  for (let attempt = 0; attempt < (force ? 3 : 1); attempt += 1) {
    const threads = await discoverAllThreads(targetDate, patterns);
    last = threads;
    const hasThaoLuan = threads.some((t) => t.forum === "thao_luan");
    if (hasThaoLuan || threads.length > 0) {
      session.discovered_threads = threads;
      return threads;
    }
    await sleep(600);
  }
  session.discovered_threads = last;
  return last;
}

async function loadOrCreateSession(targetDate: string): Promise<CollectSession> {
  const existing = await getSession(targetDate);
  if (existing) return existing;
  const settings = await getSettings();
  const { window_start, window_end } = getCollectWindow(targetDate, settings.timezone);
  return emptySession(targetDate, window_start, window_end);
}

async function fetchAndMergePage(
  thread: DiscoveredThread,
  session: CollectSession,
  page: number,
  pageUrlFor: (page: number) => string,
  startMs: number,
  endMs: number,
  firstHtml: string,
  targetDate: string,
): Promise<{ added: number; minTs: number; rowCount: number }> {
  const url = pageUrlFor(page);
  const html = page === 1 || url === thread.url ? firstHtml : await fetchForumHtml(url);
  const rows = extractPostsFromHtml(html);
  const posts = toForumPosts(rows, thread.forum, thread.slug, startMs, endMs, thread.title, targetDate);
  const added = mergePosts(session, posts);
  const minTs = rows.length
    ? Math.min(...rows.map((r) => r.posted_at_ms || Number.MAX_SAFE_INTEGER))
    : Number.MAX_SAFE_INTEGER;
  return { added, minTs, rowCount: rows.length };
}

async function crawlThreadPage(
  thread: DiscoveredThread,
  session: CollectSession,
  startMs: number,
  endMs: number,
  force: boolean,
  targetDate: string,
): Promise<number> {
  const key = threadStorageKey(thread.forum, thread.slug);
  let state = session.threads[key];
  if (!state) {
    state = {
      url: thread.url,
      title: thread.title,
      thread_slug: thread.slug,
      last_post_time: 0,
      last_page_fetched: 0,
      lowest_page_fetched: undefined,
      backfill_complete: false,
      pages_fetched_total: 0,
    };
    session.threads[key] = state;
  }

  const now = Date.now();
  const pendingBackfill = needsBackfill(state);
  if (
    !force &&
    !pendingBackfill &&
    state.last_fetch_at &&
    now - state.last_fetch_at < CRAWL_COOLDOWN_MS &&
    state.last_page_fetched > 0
  ) {
    return 0;
  }

  const firstHtml = await fetchForumHtml(thread.url);
  const lastPage = getLastPageFromHtml(firstHtml);
  const prevLastPage = state.last_page_fetched || 0;

  const pageUrlFor = (page: number): string =>
    page > 1 ? thread.url.replace(/\/?$/, `/page-${page}`) : thread.url;

  const MAX_PAGES_PER_CYCLE = force ? 999 : 25;
  let pagesFetched = 0;
  let totalAdded = 0;

  const bumpPageCount = () => {
    pagesFetched += 1;
    state.pages_fetched_total = (state.pages_fetched_total || 0) + 1;
  };

  // Thread grew — fetch new middle pages before the old last page
  if (prevLastPage > 0 && lastPage > prevLastPage) {
    for (let page = prevLastPage + 1; page < lastPage && pagesFetched < MAX_PAGES_PER_CYCLE; page += 1) {
      const { added } = await fetchAndMergePage(
        thread, session, page, pageUrlFor, startMs, endMs, firstHtml, targetDate,
      );
      totalAdded += added;
      bumpPageCount();
    }
  }

  // Always fetch last page for newest posts
  const lastUrl = pageUrlFor(lastPage);
  const lastHtml = lastPage === 1 || lastUrl === thread.url ? firstHtml : await fetchForumHtml(lastUrl);
  const lastRows = extractPostsFromHtml(lastHtml);
  const lastPosts = toForumPosts(lastRows, thread.forum, thread.slug, startMs, endMs, thread.title, targetDate);
  totalAdded += mergePosts(session, lastPosts);
  bumpPageCount();

  for (const p of lastPosts) {
    if (p.posted_at_ms > state.last_post_time) state.last_post_time = p.posted_at_ms;
  }

  state.last_page_fetched = lastPage;
  state.last_fetch_at = now;

  if (force) state.backfill_complete = false;
  if (state.lowest_page_fetched == null) state.lowest_page_fetched = lastPage;
  if ((state.lowest_page_fetched ?? lastPage) > lastPage) {
    state.lowest_page_fetched = lastPage;
  }

  const shouldBackfill =
    !state.backfill_complete &&
    startMs > 0 &&
    lastPage > 1 &&
    (state.lowest_page_fetched ?? lastPage) > 1;

  if (shouldBackfill) {
    for (
      let page = Math.min((state.lowest_page_fetched ?? lastPage) - 1, lastPage - 1);
      page >= 1;
      page -= 1
    ) {
      if (pagesFetched >= MAX_PAGES_PER_CYCLE) break;
      const { added, minTs, rowCount } = await fetchAndMergePage(
        thread, session, page, pageUrlFor, startMs, endMs, firstHtml, targetDate,
      );
      totalAdded += added;
      bumpPageCount();

      state.lowest_page_fetched = page;
      if (rowCount === 0) continue;
      if (minTs < startMs || page === 1) {
        state.backfill_complete = true;
        break;
      }
    }
  } else if (lastPage <= 1) {
    state.backfill_complete = true;
  }

  return totalAdded;
}

export async function runPollCycle(options: { force?: boolean } = {}): Promise<{ added: number; status: string }> {
  const settings = await getSettings();
  const now = new Date();
  const targetDate = getTargetDate(now, settings.timezone);
  const force = options.force === true;
  if (force) {
    clearForumHtmlCache();
    try {
      await ensureForumTab();
    } catch (e) {
      console.warn("[ForumCollector] ensureForumTab", e);
    }
  }
  const runtime = await getRuntimeStatus();
  const rolledOver = Boolean(runtime.target_date && runtime.target_date !== targetDate);

  if (rolledOver) {
    const prevSession = await getSession(runtime.target_date);
    if (prevSession) {
      const prevThreads = prevSession.discovered_threads || [];
      const { allow, coverageWarning } = canFinalizeSession(
        prevSession, prevThreads, now, runtime.target_date, settings.timezone,
      );
      if (allow || prevSession.finalized_at) {
        await finalizeCollectSession(prevSession, settings, coverageWarning);
      }
    }
  }

  const authOk = await ensureLoggedIn();
  if (!authOk) {
    await patchRuntimeStatus({
      auth_status: "error",
      last_error: "Đăng nhập forum thất bại — vẫn thử crawl nội dung công khai",
      last_poll_status: "login_retry_public",
    });
  }

  let session = await loadOrCreateSession(targetDate);
  if (rolledOver) {
    session.discovered_threads = undefined;
  }
  const inWindow = isInCollectWindow(now, targetDate, settings.timezone);

  const threadsEarly = await resolveThreads(
    targetDate,
    session,
    settings.pinned_chan_nuoi_patterns,
    force || rolledOver,
  );
  const finalizeCheck = canFinalizeSession(
    session, threadsEarly, now, targetDate, settings.timezone,
  );

  if (!force && session.finalized_at) {
    await patchRuntimeStatus({
      target_date: targetDate,
      collect_status: "finalized",
      post_count: Object.keys(session.posts).length,
      new_posts_last_poll: 0,
      last_poll_at: new Date().toISOString(),
      last_poll_status: "finalized",
    });
    return { added: 0, status: "finalized" };
  }

  if (!force && finalizeCheck.allow) {
    session.summary = buildSummary(session, settings);
    await finalizeCollectSession(session, settings, finalizeCheck.coverageWarning);
    await saveSession(session);
    await patchRuntimeStatus({
      target_date: targetDate,
      collect_status: "finalized",
      post_count: Object.keys(session.posts).length,
      new_posts_last_poll: 0,
      last_poll_at: new Date().toISOString(),
      last_poll_status: finalizeCheck.coverageWarning ? "finalized_coverage_warning" : "finalized",
    });
    return { added: 0, status: "finalized" };
  }

  const afterFinalizeTime = shouldFinalize(now, targetDate, settings.timezone);
  if (!force && !inWindow && !afterFinalizeTime) {
    await patchRuntimeStatus({
      target_date: targetDate,
      collect_status: "idle",
      post_count: Object.keys(session.posts).length,
      new_posts_last_poll: 0,
      last_poll_status: "outside_window",
      last_poll_at: new Date().toISOString(),
    });
    return { added: 0, status: "outside_window" };
  }

  const { startMs, endMs } = force
    ? { startMs: 0, endMs: Number.MAX_SAFE_INTEGER }
    : getWindowBoundsMs(targetDate, settings.timezone);
  const threads = threadsEarly;
  const missingThaoLuan = !threads.some((t) => t.forum === "thao_luan");

  if (missingThaoLuan && threads.length === 0) {
    await patchRuntimeStatus({
      target_date: targetDate,
      collect_status: "waiting_thread",
      last_poll_at: new Date().toISOString(),
      last_poll_status: "waiting_thread",
    });
    await saveSession(session);
    return { added: 0, status: "waiting_thread" };
  }

  let totalAdded = 0;
  let crawlError = "";
  for (const thread of threads) {
    try {
      totalAdded += await crawlThreadPage(thread, session, startMs, endMs, force, targetDate);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      if (!crawlError) crawlError = `${thread.forum}: ${msg}`;
      if (msg === "LOGIN_FAILED" || msg === "NOT_LOGGED_IN") {
        await ensureLoggedIn();
      }
      console.warn("[ForumCollector] thread crawl error", thread.url, msg);
    }
  }

  session.summary = buildSummary(session, settings);
  await saveSession(session);
  const postCount = Object.keys(session.posts).length;

  // When the user clicks "Poll ngay" (force), ensure Thảo luận is actually present;
  // otherwise UI like đề top 4 can look "empty" even though forum has data.
  if (force) {
    const tlCount = thaoLuanPostCount(session);
    if (tlCount === 0) {
      await patchRuntimeStatus({
        last_error:
          "Poll xong nhưng không có post Thảo luận — mở thread Thảo luận trong Chrome rồi Poll lại.",
      });
    } else if (!thaoLuanHasDeSignals(session)) {
      await patchRuntimeStatus({
        last_error:
          "Thảo luận đã có post nhưng chưa parse được chốt đề (BTD/BTĐ/STĐ/Chạm/Tổng/Đầu). Thử Poll lại sau 1–2 phút.",
      });
    }
  }

  if ((settings.auto_sync || force) && postCount > 0) {
    await syncSessionToApi(session);
  }
  await pruneOldSessions();

  const stillBackfilling = dailyThreadsNeedBackfill(session, threads);
  const collectStatus = stillBackfilling && afterFinalizeTime ? "backfilling" : "collecting";

  await patchRuntimeStatus({
    target_date: targetDate,
    collect_status: collectStatus,
    post_count: Object.keys(session.posts).length,
    new_posts_last_poll: totalAdded,
    last_poll_at: new Date().toISOString(),
    last_error:
      postCount === 0 && crawlError
        ? crawlError
        : postCount === 0 && totalAdded === 0
          ? "Không lấy được post — mở forumketqua.net trong Chrome rồi Poll lại"
          : undefined,
    last_poll_status: rolledOver
      ? "rolled_over"
      : missingThaoLuan
        ? `waiting_thread (+${totalAdded})`
        : stillBackfilling && afterFinalizeTime
          ? `backfilling (+${totalAdded})`
          : `collecting (+${totalAdded})`,
  });

  return { added: totalAdded, status: collectStatus };
}

export async function setupAlarms(): Promise<void> {
  const settings = await getSettings();
  const now = new Date();
  const targetDate = getTargetDate(now, settings.timezone);
  const inWindow = isInCollectWindow(now, targetDate, settings.timezone);
  const afterFinalize = shouldFinalize(now, targetDate, settings.timezone);
  const minutes = inWindow || afterFinalize
    ? settings.poll_interval_active_min
    : settings.poll_interval_idle_min;

  await chrome.alarms.clear("rbk-poll");
  chrome.alarms.create("rbk-poll", { periodInMinutes: minutes });

  await chrome.alarms.clear("rbk-rollover");
  chrome.alarms.create("rbk-rollover", { when: getNextRolloverMs(now, settings.timezone) });
}
