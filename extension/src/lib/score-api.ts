import type { ExtensionSettings } from "../types/forum.js";
import { getSettings } from "./storage.js";

export interface DrawScoreResultRow {
  username: string;
  pick_type: string;
  numbers: string[];
  hit: boolean;
  posted_at?: string;
  forum?: string;
  thread_url?: string;
  evaluated_at?: string;
}

export interface DrawScoreResponse {
  target_date: string;
  ok: boolean;
  error?: string;
  cutoff?: string;
  imported?: boolean;
  draw?: {
    de?: string | null;
    db?: string | null;
    loto?: string[];
    source?: string;
  };
  summary?: {
    hits: number;
    total: number;
    hit_rate_pct: number;
    skipped_after_cutoff?: number;
  };
  results?: DrawScoreResultRow[];
}

const FALLBACK_BASES = [
  "http://localhost:18715",
  "http://127.0.0.1:18715",
];

function apiBases(settings: ExtensionSettings): string[] {
  const primary = settings.api_base_url.replace(/\/$/, "");
  return [primary, ...FALLBACK_BASES.filter((b) => b !== primary)];
}

async function fetchJson(base: string, path: string): Promise<DrawScoreResponse> {
  const res = await fetch(`${base}${path}`, { headers: { Accept: "application/json" } });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text.slice(0, 120)}`);
  }
  return res.json() as Promise<DrawScoreResponse>;
}

export async function fetchDrawScore(
  targetDate: string,
  settings?: ExtensionSettings,
): Promise<DrawScoreResponse> {
  const s = settings || (await getSettings());
  const path = `/forum/score?target_date=${encodeURIComponent(targetDate)}`;
  let lastError: Error | null = null;
  for (const base of apiBases(s)) {
    try {
      return await fetchJson(base, path);
    } catch (e) {
      lastError = e instanceof Error ? e : new Error(String(e));
    }
  }
  throw lastError || new Error("Không kết nối API");
}

export async function runDrawScore(
  targetDate: string,
  settings?: ExtensionSettings,
): Promise<DrawScoreResponse> {
  const s = settings || (await getSettings());
  const path = `/forum/score/run?target_date=${encodeURIComponent(targetDate)}`;
  let lastError: Error | null = null;
  for (const base of apiBases(s)) {
    try {
      return await fetchJson(base, path);
    } catch (e) {
      lastError = e instanceof Error ? e : new Error(String(e));
    }
  }
  throw lastError || new Error("Không kết nối API");
}
