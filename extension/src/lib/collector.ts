import type { CollectSession, DiscoveredThread, ForumKey } from "../types/forum.js";
import {
  getCollectWindow,
  getTargetDate,
  getWindowBoundsMs,
  isInCollectWindow,
  isSunday,
  shouldFinalize,
} from "./date-window.js";
import { ensureLoggedIn, fetchForumHtml } from "./forum-auth.js";
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
  patchRuntimeStatus,
  pruneOldSessions,
  saveSession,
} from "./storage.js";

function threadStorageKey(forum: ForumKey, slug: string): string {
  return forum === "chan_nuoi" ? `chan_nuoi:${slug}` : forum;
}

const CRAWL_COOLDOWN_MS = 5 * 60 * 1000;

async function resolveThreads(
  targetDate: string,
  session: CollectSession,
  patterns: string[],
  force: boolean,
): Promise<DiscoveredThread[]> {
  if (!force && session.discovered_threads?.length) {
    return session.discovered_threads;
  }
  const threads = await discoverAllThreads(targetDate, patterns);
  session.discovered_threads = threads;
  return threads;
}

async function loadOrCreateSession(targetDate: string): Promise<CollectSession> {
  const existing = await getSession(targetDate);
  if (existing) return existing;
  const settings = await getSettings();
  const { window_start, window_end } = getCollectWindow(targetDate, settings.timezone);
  return emptySession(targetDate, window_start, window_end);
}

async function crawlThreadPage(
  thread: DiscoveredThread,
  session: CollectSession,
  startMs: number,
  endMs: number,
  force: boolean,
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
    };
    session.threads[key] = state;
  }

  const now = Date.now();
  if (
    !force &&
    state.last_fetch_at &&
    now - state.last_fetch_at < CRAWL_COOLDOWN_MS &&
    state.last_page_fetched > 0
  ) {
    return 0;
  }

  const firstHtml = await fetchForumHtml(thread.url);
  const lastPage = getLastPageFromHtml(firstHtml);

  const pageUrlFor = (page: number): string =>
    page > 1 ? thread.url.replace(/\/?$/, `/page-${page}`) : thread.url;

  const MAX_PAGES_PER_CYCLE = force ? 999 : 25; // avoid runaway threads; daily threads typically <= 15 pages
  let pagesFetched = 0;
  let totalAdded = 0;

  // Always fetch last page to get newest posts
  const lastUrl = pageUrlFor(lastPage);
  const lastHtml = lastUrl === thread.url ? firstHtml : await fetchForumHtml(lastUrl);
  pagesFetched += 1;

  const lastRows = extractPostsFromHtml(lastHtml);
  const lastPosts = toForumPosts(lastRows, thread.forum, thread.slug, startMs, endMs, thread.title);
  totalAdded += mergePosts(session, lastPosts);

  for (const p of lastPosts) {
    if (p.posted_at_ms > state.last_post_time) state.last_post_time = p.posted_at_ms;
  }

  state.last_page_fetched = lastPage;
  state.last_fetch_at = now;

  // Backfill older pages to avoid confusing counts + improve recommendations
  if (force) state.backfill_complete = false;
  if (state.lowest_page_fetched == null) state.lowest_page_fetched = lastPage;

  const shouldBackfill =
    !state.backfill_complete &&
    startMs > 0 && // no need for infinite window
    lastPage > 1 &&
    state.lowest_page_fetched > 1;

  if (!shouldBackfill) return totalAdded;

  // Crawl backwards until we reach window start (or hit max pages)
  for (let page = Math.min(state.lowest_page_fetched - 1, lastPage - 1); page >= 1; page -= 1) {
    if (pagesFetched >= MAX_PAGES_PER_CYCLE) break;
    const url = pageUrlFor(page);
    const html = await fetchForumHtml(url);
    pagesFetched += 1;

    const rows = extractPostsFromHtml(html);
    if (!rows.length) {
      state.lowest_page_fetched = page;
      continue;
    }

    const posts = toForumPosts(rows, thread.forum, thread.slug, startMs, endMs, thread.title);
    totalAdded += mergePosts(session, posts);

    // Stop once this page already contains older-than-window content (earlier pages are even older)
    const minTs = Math.min(...rows.map((r) => r.posted_at_ms || Number.MAX_SAFE_INTEGER));
    state.lowest_page_fetched = page;
    if (minTs < startMs || page === 1) {
      state.backfill_complete = true;
      break;
    }
  }

  return totalAdded;
}

export async function runPollCycle(options: { force?: boolean } = {}): Promise<{ added: number; status: string }> {
  const settings = await getSettings();
  const now = new Date();
  const targetDate = getTargetDate(now, settings.timezone);
  const force = options.force === true;

  if (isSunday(targetDate)) {
    await patchRuntimeStatus({
      target_date: targetDate,
      collect_status: "sunday_skip",
      new_posts_last_poll: 0,
      last_poll_status: "sunday_skip",
    });
    return { added: 0, status: "sunday_skip" };
  }

  const loggedIn = await ensureLoggedIn();
  if (!loggedIn) {
    await patchRuntimeStatus({
      collect_status: "idle",
      last_error: "Login failed",
      last_poll_status: "login_failed",
      last_poll_at: new Date().toISOString(),
    });
    return { added: 0, status: "login_failed" };
  }

  let session = await loadOrCreateSession(targetDate);
  const inWindow = isInCollectWindow(now, targetDate, settings.timezone);
  const finalize = !force && shouldFinalize(now, targetDate, settings.timezone);

  if (!force && (session.finalized_at || finalize)) {
    session.summary = buildSummary(session, settings);
    if (!session.finalized_at) {
      session.finalized_at = new Date().toISOString();
      await syncSessionToApi(session);
    }
    await saveSession(session);
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

  if (!force && !inWindow) {
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
  const threads = await resolveThreads(targetDate, session, settings.pinned_chan_nuoi_patterns, force);

  if (!threads.some((t) => t.forum === "thao_luan")) {
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
  for (const thread of threads) {
    try {
      totalAdded += await crawlThreadPage(thread, session, startMs, endMs, force);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      if (msg === "LOGIN_FAILED" || msg === "NOT_LOGGED_IN") {
        await ensureLoggedIn();
      }
      console.warn("[ForumCollector] thread crawl error", thread.url, msg);
    }
  }

  session.summary = buildSummary(session, settings);
  await saveSession(session);
  if (settings.auto_sync) {
    await syncSessionToApi(session);
  }
  await pruneOldSessions();

  await patchRuntimeStatus({
    target_date: targetDate,
    collect_status: "collecting",
    post_count: Object.keys(session.posts).length,
    new_posts_last_poll: totalAdded,
    last_poll_at: new Date().toISOString(),
    last_error: undefined,
    last_poll_status: `collecting (+${totalAdded})`,
  });

  return { added: totalAdded, status: "collecting" };
}

export async function setupAlarms(): Promise<void> {
  const settings = await getSettings();
  const now = new Date();
  const inWindow = isInCollectWindow(now, getTargetDate(now, settings.timezone), settings.timezone);
  const minutes = inWindow
    ? settings.poll_interval_active_min
    : settings.poll_interval_idle_min;

  await chrome.alarms.clear("rbk-poll");
  chrome.alarms.create("rbk-poll", { periodInMinutes: minutes });
}
