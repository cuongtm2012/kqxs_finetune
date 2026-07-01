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

function get<T>(key: string): Promise<T | undefined> {
  return new Promise((resolve) => {
    chrome.storage.local.get(key, (data) => resolve(data[key] as T | undefined));
  });
}

function set(obj: Record<string, unknown>): Promise<void> {
  return new Promise((resolve) => chrome.storage.local.set(obj, resolve));
}

export async function getSettings(): Promise<ExtensionSettings> {
  const s = await get<ExtensionSettings>(STORAGE_KEYS.settings);
  return { ...DEFAULT_SETTINGS, ...s };
}

export async function saveSettings(partial: Partial<ExtensionSettings>): Promise<ExtensionSettings> {
  const current = await getSettings();
  const next = { ...current, ...partial };
  await set({ [STORAGE_KEYS.settings]: next });
  return next;
}

export async function getForumAuth(): Promise<ForumAuth> {
  const a = await get<ForumAuth>(STORAGE_KEYS.forumAuth);
  return { ...DEFAULT_FORUM_AUTH, ...a };
}

export async function saveForumAuth(auth: Partial<ForumAuth>): Promise<ForumAuth> {
  const current = await getForumAuth();
  const next = { ...current, ...auth };
  await set({ [STORAGE_KEYS.forumAuth]: next });
  return next;
}

export async function seedDefaultsOnInstall(): Promise<void> {
  const existing = await get<ForumAuth>(STORAGE_KEYS.forumAuth);
  if (!existing) await set({ [STORAGE_KEYS.forumAuth]: DEFAULT_FORUM_AUTH });
  const settings = await get<ExtensionSettings>(STORAGE_KEYS.settings);
  if (!settings) await set({ [STORAGE_KEYS.settings]: DEFAULT_SETTINGS });
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
