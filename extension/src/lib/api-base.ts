import type { ExtensionSettings } from "../types/forum.js";
import { getSettings, saveSettings } from "./storage.js";

/** Prefer 127.0.0.1 — Chrome/macOS often resolves localhost → ::1 while uvicorn binds IPv4 only. */
export const FALLBACK_BASES = [
  "http://127.0.0.1:18715",
  "http://localhost:18715",
  "http://127.0.0.1:8081",
  "http://localhost:8081",
];

export const DEFAULT_API_BASE = FALLBACK_BASES[0];

export interface ApiFetchResult {
  ok: boolean;
  status: number;
  body: string;
  error?: string;
}

export function normalizeApiBase(url: string): string {
  const trimmed = (url || "").trim().replace(/\/$/, "");
  if (!trimmed || !/^https?:\/\//i.test(trimmed)) {
    return DEFAULT_API_BASE;
  }
  return trimmed.replace("://localhost", "://127.0.0.1");
}

export function apiBases(settings: Pick<ExtensionSettings, "api_base_url">): string[] {
  const primary = normalizeApiBase(settings.api_base_url);
  return [primary, ...FALLBACK_BASES.filter((b) => b !== primary)];
}

function fetchTimeoutSignal(ms: number): AbortSignal {
  if (typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function") {
    return AbortSignal.timeout(ms);
  }
  const ctrl = new AbortController();
  setTimeout(() => ctrl.abort(), ms);
  return ctrl.signal;
}

/** Fetch via background service worker — reliable for localhost from extension popup. */
export async function apiFetch(
  url: string,
  init: {
    method?: string;
    headers?: Record<string, string>;
    body?: string;
    timeoutMs?: number;
  } = {},
): Promise<ApiFetchResult> {
  const timeoutMs = init.timeoutMs ?? 15_000;

  if (typeof chrome !== "undefined" && chrome.runtime?.sendMessage) {
    try {
      const result = (await chrome.runtime.sendMessage({
        type: "API_FETCH",
        url,
        method: init.method || "GET",
        headers: init.headers,
        body: init.body,
        timeoutMs,
      })) as ApiFetchResult | undefined;

      if (!result) {
        return { ok: false, status: 0, body: "", error: "Không phản hồi từ background worker" };
      }
      return result;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      return { ok: false, status: 0, body: "", error: msg };
    }
  }

  try {
    const res = await fetch(url, {
      method: init.method || "GET",
      headers: init.headers,
      body: init.body,
      signal: fetchTimeoutSignal(timeoutMs),
    });
    const body = await res.text();
    return { ok: res.ok, status: res.status, body };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { ok: false, status: 0, body: "", error: msg };
  }
}

export async function apiFetchJson<T>(
  url: string,
  init: {
    method?: string;
    headers?: Record<string, string>;
    body?: string;
    timeoutMs?: number;
  } = {},
): Promise<T> {
  const res = await apiFetch(url, init);
  if (res.error) {
    throw new Error(res.error);
  }
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${res.body.slice(0, 160)}`);
  }
  return JSON.parse(res.body) as T;
}

export async function pingApiBase(base: string, timeoutMs = 5000): Promise<boolean> {
  try {
    const res = await apiFetch(`${normalizeApiBase(base)}/health`, {
      method: "GET",
      headers: { Accept: "application/json" },
      timeoutMs,
    });
    if (res.error || !res.ok) return false;
    const data = JSON.parse(res.body) as { status?: string };
    return data.status === "ok";
  } catch {
    return false;
  }
}

let lastPingCache: {
  at: number;
  online: boolean;
  base: string | null;
  settings: ExtensionSettings;
} | null = null;

const PING_CACHE_MS = 8_000;

/** Find a reachable API base; persist working URL to settings. */
export async function resolveWorkingApiBase(
  settings?: ExtensionSettings,
  options: { force?: boolean } = {},
): Promise<{ online: boolean; base: string | null; settings: ExtensionSettings; error?: string }> {
  const now = Date.now();
  if (!options.force && lastPingCache && now - lastPingCache.at < PING_CACHE_MS) {
    return lastPingCache;
  }

  const s = settings || (await getSettings());
  const normalized = normalizeApiBase(s.api_base_url);
  let current = s;
  if (normalized !== s.api_base_url.replace(/\/$/, "")) {
    current = await saveSettings({ api_base_url: normalized });
  }

  let lastError = "";
  for (const base of apiBases(current)) {
    const res = await apiFetch(`${normalizeApiBase(base)}/health`, {
      method: "GET",
      headers: { Accept: "application/json" },
      timeoutMs: 5000,
    });
    if (res.error) {
      lastError = res.error;
      continue;
    }
    if (!res.ok) {
      lastError = `HTTP ${res.status}`;
      continue;
    }
    try {
      const data = JSON.parse(res.body) as { status?: string };
      if (data.status !== "ok") {
        lastError = "health not ok";
        continue;
      }
    } catch {
      lastError = "invalid health JSON";
      continue;
    }

    const hit = normalizeApiBase(base);
    if (hit !== normalizeApiBase(current.api_base_url)) {
      current = await saveSettings({ api_base_url: hit });
    }
    lastPingCache = { at: now, online: true, base: hit, settings: current };
    return lastPingCache;
  }

  lastPingCache = {
    at: now,
    online: false,
    base: null,
    settings: current,
    error: lastError || "no API",
  };
  return lastPingCache;
}

/** Ensure settings point to a working base before API calls. */
export async function ensureApiOnline(settings?: ExtensionSettings): Promise<ExtensionSettings> {
  const resolved = await resolveWorkingApiBase(settings, { force: true });
  if (!resolved.online) {
    throw new Error(
      resolved.error
        ? `Không kết nối API (${resolved.error}) — chạy: APP_PORT=18715 python run.py`
        : "Không kết nối API — chạy: APP_PORT=18715 python run.py",
    );
  }
  return resolved.settings;
}
