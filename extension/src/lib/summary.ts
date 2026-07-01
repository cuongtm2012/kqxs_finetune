import type {
  CollectSession,
  ExtensionSettings,
  ForumDaySummary,
  ForumPost,
} from "../types/forum.js";
import { weekdayVi } from "./date-window.js";
import { canonicalUsername } from "./expert-aliases.js";
import { danSizeLabel, inferDanPickType } from "./pick-parser.js";

function freqMap(
  entries: [string, string][],
): Record<string, { count: number; users: string[] }> {
  const map: Record<string, { count: number; users: string[] }> = {};
  for (const [num, user] of entries) {
    if (!map[num]) map[num] = { count: 0, users: [] };
    map[num].count += 1;
    if (!map[num].users.includes(user)) map[num].users.push(user);
  }
  return Object.fromEntries(
    Object.entries(map).sort((a, b) => b[1].count - a[1].count),
  );
}

export function buildSummary(
  session: CollectSession,
  settings: ExtensionSettings,
): ForumDaySummary {
  const posts = Object.values(session.posts);
  const targetUsers = new Set(settings.target_users);

  const stl_k2n_users: ForumDaySummary["stl_k2n_users"] = {};
  const btl_k3n_users: ForumDaySummary["btl_k3n_users"] = {};
  const daily_users: ForumDaySummary["daily_users"] = {};
  let muc_lo: ForumDaySummary["muc_lo"] = {};
  let dan_de: string[] = [];
  const danMap = new Map<string, ForumDaySummary["dan_board"][0] & { _ts: number }>();
  const de_cham_leaders: ForumDaySummary["de_cham_leaders"] = [];
  const stlPairs: [string, string][] = [];
  const btlPairs: [string, string][] = [];

  const forumCounts = {
    mo_bat: 0,
    thao_luan: 0,
    chan_nuoi: 0,
  };

  for (const p of posts) {
    const user = canonicalUsername(p.user);
    forumCounts[p.forum] += 1;
    const isChanNuoi = p.forum === "chan_nuoi";
    const isDaily = p.forum === "thao_luan" || p.forum === "mo_bat";

    if (p.picks.muc_lo && Object.keys(p.picks.muc_lo).length) {
      muc_lo = p.picks.muc_lo;
    }
    if (p.picks.dan_de?.length) {
      const threadKey =
        p.forum === "chan_nuoi" ? `chan_nuoi:${p.thread_id}` : p.forum;
      const threadTitle = session.threads[threadKey]?.title || p.thread_id;
      const pickType =
        p.picks.dan_pick_type ||
        inferDanPickType(p.picks.dan_de.length, threadTitle, p.raw_content);
      dan_de = p.picks.dan_de;
      const key = `${user}|${pickType}`;
      const prev = danMap.get(key);
      if (!prev || p.posted_at_ms >= prev._ts) {
        danMap.set(key, {
          user,
          pick_type: pickType,
          size: danSizeLabel(pickType),
          count: p.picks.dan_de.length,
          numbers: p.picks.dan_de,
          _ts: p.posted_at_ms,
        });
      }
    }

    if (p.picks.stl?.length) {
      if (isChanNuoi && targetUsers.has(user)) {
        stl_k2n_users[user] = { stl: p.picks.stl, raw: p.raw_content.slice(0, 200) };
      }
      if (targetUsers.has(user)) {
        for (const n of p.picks.stl) stlPairs.push([n, user]);
      }
    }

    if (p.picks.btl?.length) {
      if (isChanNuoi && targetUsers.has(user)) {
        btl_k3n_users[user] = { btl: p.picks.btl, raw: p.raw_content.slice(0, 200) };
      }
      if (targetUsers.has(user)) {
        for (const n of p.picks.btl) btlPairs.push([n, user]);
      }
    }

    if (
      isDaily &&
      targetUsers.has(user) &&
      (p.picks.stl?.length || p.picks.btl?.length || p.picks.de)
    ) {
      daily_users[user] = {
        stl: p.picks.stl || [],
        btl: p.picks.btl || [],
        de: p.picks.de,
      };
      if (p.picks.de?.cham?.length) {
        de_cham_leaders.push({ user, cham: p.picks.de.cham });
      }
    }
  }

  const dan_board = [...danMap.values()].map(({ _ts, ...d }) => d);

  const moThread = session.threads["mo_bat"];
  const tlThread = session.threads["thao_luan"];
  const cnThreads = Object.entries(session.threads)
    .filter(([k]) => k.startsWith("chan_nuoi:"))
    .map(([, v]) => ({ url: v.url, title: v.title }));

  return {
    date: session.target_date,
    weekday: weekdayVi(session.target_date),
    target_date: session.target_date,
    collected_at: new Date().toISOString(),
    forums: {
      mo_bat: moThread
        ? { thread_url: moThread.url, post_count: forumCounts.mo_bat }
        : undefined,
      thao_luan: tlThread
        ? { thread_url: tlThread.url, post_count: forumCounts.thao_luan }
        : undefined,
      chan_nuoi: cnThreads.length
        ? { threads: cnThreads, post_count: forumCounts.chan_nuoi }
        : undefined,
    },
    stl_k2n_users,
    btl_k3n_users,
    daily_users,
    muc_lo,
    dan_de,
    dan_board,
    de_cham_leaders,
    stl_frequency: freqMap(stlPairs),
    btl_frequency: freqMap(btlPairs),
    all_posts: posts,
  };
}

export function emptySession(
  targetDate: string,
  windowStart: string,
  windowEnd: string,
): CollectSession {
  return {
    target_date: targetDate,
    window_start: windowStart,
    window_end: windowEnd,
    threads: {},
    posts: {},
    summary: {
      date: targetDate,
      weekday: weekdayVi(targetDate),
      target_date: targetDate,
      forums: {},
      stl_k2n_users: {},
      btl_k3n_users: {},
      daily_users: {},
      muc_lo: {},
      dan_de: [],
      dan_board: [],
      de_cham_leaders: [],
      stl_frequency: {},
      btl_frequency: {},
    },
  };
}

export function mergePosts(
  session: CollectSession,
  incoming: ForumPost[],
): number {
  let added = 0;
  for (const p of incoming) {
    if (session.posts[p.post_id]) continue;
    session.posts[p.post_id] = p;
    added += 1;
  }
  return added;
}
