import type {
  CollectSession,
  ExtensionSettings,
  ForumAuth,
  RuntimeStatus,
} from "../types/forum.js";
import {
  DEFAULT_FORUM_AUTH,
  DEFAULT_SETTINGS,
  STORAGE_KEYS,
} from "../types/forum.js";
import { apiBases, apiFetch, normalizeApiBase, DEFAULT_API_BASE } from "./api-base.js";

function get<T>(key: string): Promise<T | undefined> {
  return new Promise((resolve) => {
    chrome.storage.local.get(key, (data) => resolve(data[key] as T | undefined));
  });
}

function set(obj: Record<string, unknown>): Promise<void> {
  return new Promise((resolve) => chrome.storage.local.set(obj, resolve));
}

function mergeWithDefaults<T extends Record<string, unknown>>(defaults: T, stored?: Partial<T>): T {
  const out = { ...defaults };
  if (!stored) return out;
  for (const key of Object.keys(defaults) as (keyof T)[]) {
    const v = stored[key];
    if (v !== undefined && v !== null && v !== "") {
      out[key] = v as T[keyof T];
    }
  }
  return out;
}

export async function getSettings(): Promise<ExtensionSettings> {
  const s = await get<ExtensionSettings>(STORAGE_KEYS.settings);
  return mergeWithDefaults(DEFAULT_SETTINGS, s);
}

export async function saveSettings(partial: Partial<ExtensionSettings>): Promise<ExtensionSettings> {
  const current = await getSettings();
  const next = { ...current, ...partial };
  await set({ [STORAGE_KEYS.settings]: next });
  return next;
}

export async function getForumAuth(): Promise<ForumAuth> {
  const a = await get<ForumAuth>(STORAGE_KEYS.forumAuth);
  return mergeWithDefaults(DEFAULT_FORUM_AUTH, a);
}

export async function saveForumAuth(auth: Partial<ForumAuth>): Promise<ForumAuth> {
  const current = await getForumAuth();
  const next = { ...current, ...auth };
  await set({ [STORAGE_KEYS.forumAuth]: next });
  return next;
}

/** Ghi credentials/settings mặc định nếu storage trống hoặc thiếu field quan trọng. */
export async function ensureConfigSeeded(): Promise<void> {
  const auth = await getForumAuth();
  const storedAuth = await get<ForumAuth>(STORAGE_KEYS.forumAuth);
  if (!storedAuth?.username || !storedAuth?.password) {
    await set({ [STORAGE_KEYS.forumAuth]: auth });
  }
  const settings = await getSettings();
  const storedSettings = await get<ExtensionSettings>(STORAGE_KEYS.settings);
  const normalizedUrl = normalizeApiBase(settings.api_base_url || DEFAULT_API_BASE);
  if (
    !storedSettings?.api_base_url ||
    storedSettings.api_base_url.includes("localhost") ||
    !/^https?:\/\//i.test(storedSettings.api_base_url)
  ) {
    await set({ [STORAGE_KEYS.settings]: { ...settings, api_base_url: normalizedUrl } });
  }
}

export async function seedDefaultsOnInstall(): Promise<void> {
  await ensureConfigSeeded();
}

export function sessionKey(targetDate: string): string {
  return `${STORAGE_KEYS.sessionPrefix}${targetDate}`;
}

export async function getSession(targetDate: string): Promise<CollectSession | undefined> {
  return get<CollectSession>(sessionKey(targetDate));
}

export async function saveSession(session: CollectSession): Promise<void> {
  await set({ [sessionKey(session.target_date)]: session });
}

export async function getRuntimeStatus(): Promise<RuntimeStatus> {
  const r = await get<RuntimeStatus>(STORAGE_KEYS.runtime);
  return (
    r || {
      auth_status: "not_logged_in",
      target_date: "",
      collect_status: "idle",
      post_count: 0,
      new_posts_last_poll: 0,
    }
  );
}

export async function patchRuntimeStatus(partial: Partial<RuntimeStatus>): Promise<RuntimeStatus> {
  const current = await getRuntimeStatus();
  const next = { ...current, ...partial };
  await set({ [STORAGE_KEYS.runtime]: next });
  return next;
}

export async function pruneOldSessions(keepDays = 30): Promise<void> {
  const all = await new Promise<Record<string, unknown>>((resolve) => {
    chrome.storage.local.get(null, resolve);
  });
  const cutoff = Date.now() - keepDays * 86_400_000;
  const toRemove: string[] = [];
  for (const [key, val] of Object.entries(all)) {
    if (!key.startsWith(STORAGE_KEYS.sessionPrefix)) continue;
    const session = val as CollectSession;
    const end = Date.parse(session.window_end);
    if (!Number.isNaN(end) && end < cutoff) toRemove.push(key);
  }
  if (toRemove.length) {
    await new Promise<void>((resolve) => chrome.storage.local.remove(toRemove, resolve));
  }
}

export async function clearSession(targetDate: string): Promise<void> {
  await new Promise<void>((resolve) =>
    chrome.storage.local.remove(sessionKey(targetDate), resolve),
  );
}

export async function listSessionDates(): Promise<string[]> {
  const all = await new Promise<Record<string, unknown>>((resolve) => {
    chrome.storage.local.get(null, resolve);
  });
  return Object.keys(all)
    .filter((k) => k.startsWith(STORAGE_KEYS.sessionPrefix))
    .map((k) => k.replace(STORAGE_KEYS.sessionPrefix, ""))
    .sort()
    .reverse();
}

export type RecoExpertSortMode = "weight" | "performance" | "effective";

export type RecoScoringMode = "weight" | "measured" | "blend";

const RECO_EXPERT_SORT_KEY = "reco_expert_sort";
const RECO_SCORING_MODE_KEY = "reco_scoring_mode";

export async function getRecoScoringMode(): Promise<RecoScoringMode> {
  const v = await get<string>(RECO_SCORING_MODE_KEY);
  if (v === "weight" || v === "measured") return v;
  return "blend";
}

export async function saveRecoScoringMode(mode: RecoScoringMode): Promise<void> {
  await set({ [RECO_SCORING_MODE_KEY]: mode });
}

export async function getRecoExpertSort(): Promise<RecoExpertSortMode> {
  const v = await get<string>(RECO_EXPERT_SORT_KEY);
  if (v === "performance") return "performance";
  if (v === "effective") return "effective";
  return "weight";
}

export async function saveRecoExpertSort(mode: RecoExpertSortMode): Promise<void> {
  await set({ [RECO_EXPERT_SORT_KEY]: mode });
}
