import type { ExtensionSettings } from "../types/forum.js";
import { apiBases, apiFetch, normalizeApiBase } from "./api-base.js";
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

export interface ScoreCoverageThread {
  key: string;
  backfill_complete?: boolean;
  lowest_page_fetched?: number;
  last_page_fetched?: number;
  thread_slug?: string;
}

export interface ScoreCoverage {
  threads?: ScoreCoverageThread[];
  post_count?: number;
  coverage_warning?: boolean;
}

export interface DrawScoreResponse {
  target_date: string;
  ok: boolean;
  error?: string;
  cutoff?: string;
  imported?: boolean;
  coverage?: ScoreCoverage;
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

async function fetchJson(
  base: string,
  path: string,
  method: "GET" | "POST" = "GET",
): Promise<DrawScoreResponse> {
  const res = await apiFetch(`${base}${path}`, {
    method,
    headers: { Accept: "application/json" },
  });
  if (res.error) throw new Error(res.error);
  if (res.status === 404) {
    throw new Error(`API ${base} thiếu /forum/score — restart: APP_PORT=18715 python run.py`);
  }
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${res.body.slice(0, 120)}`);
  }
  return JSON.parse(res.body) as DrawScoreResponse;
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
      return await fetchJson(base, path, "POST");
    } catch (e) {
      lastError = e instanceof Error ? e : new Error(String(e));
    }
  }
  throw lastError || new Error("Không kết nối API");
}
