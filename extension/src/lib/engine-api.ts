import type { ExtensionSettings } from "../types/forum.js";
import { apiBases, apiFetchJson, normalizeApiBase } from "./api-base.js";
import { getSettings, saveSettings } from "./storage.js";

export interface CandidateRow {
  loto: string;
  score: number;
  filters_matched: number;
  reasons?: string[];
}

export interface CandidatesResponse {
  endpoint?: string;
  target: string;
  target_date: string;
  as_of_date: string;
  disclaimer?: string;
  context?: Record<string, unknown>;
  candidates: CandidateRow[];
  meta?: Record<string, unknown>;
}

export interface IntersectionPick {
  loto: string;
  lift?: number;
  count?: number;
  cau_count?: number;
  source?: string;
}

export interface IntersectionResponse {
  module?: string;
  target_date: string;
  as_of_date: string;
  yesterday_db?: string;
  strategy?: string;
  cf_candidates?: IntersectionPick[];
  rbk_candidates?: Array<IntersectionPick | string>;
  intersection?: IntersectionPick[];
  final_picks?: Array<IntersectionPick | string>;
}

export interface PredictionRow {
  rank: number;
  value: string;
  score: number;
}

export interface PredictionsResponse {
  target_date: string;
  as_of_date?: string;
  target_type: string;
  model: string;
  disclaimer?: string;
  predictions: PredictionRow[];
}

export interface AnalyticsStats {
  mb_draws: number;
  oldest: string | null;
  newest: string | null;
  mb_prizes?: number;
}

export interface EngineBundle {
  target_date: string;
  as_of_date: string;
  api_base: string;
  analytics: AnalyticsStats | null;
  stats_loto: CandidatesResponse;
  stats_de: CandidatesResponse;
  intersection: IntersectionResponse;
  predictions: PredictionsResponse | null;
}

async function fetchJson<T>(url: string): Promise<T> {
  return apiFetchJson<T>(url, { headers: { Accept: "application/json" } });
}

async function fetchEngineFromBase(base: string): Promise<EngineBundle> {
  const q = (path: string, params: Record<string, string | number | boolean>) => {
    const sp = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) sp.set(k, String(v));
    return `${base}${path}?${sp}`;
  };

  // Không truyền target_date — API tự lấy MAX(draw_date) trong DB + 1 ngày.
  // Tránh lệch với lịch forum khi KQXS chưa import kịp.
  const [stats_loto, stats_de, intersection] = await Promise.all([
    fetchJson<CandidatesResponse>(
      q("/stats/candidates", { target: "loto", top: 15, min_filters: 1, sort: "score" }),
    ),
    fetchJson<CandidatesResponse>(
      q("/stats/candidates", { target: "de", top: 10, min_filters: 1, sort: "score" }),
    ),
    fetchJson<IntersectionResponse>(
      q("/stats/intersection", { top: 15, strategy: "intersection" }),
    ),
  ]);

  let predictions: PredictionsResponse | null = null;
  try {
    predictions = await fetchJson<PredictionsResponse>(
      q("/predictions/next", { target: "loto", top: 10, model: "ensemble", persist: false }),
    );
  } catch {
    predictions = null;
  }

  let analytics: AnalyticsStats | null = null;
  try {
    analytics = await fetchJson<AnalyticsStats>(`${base}/analytics/stats`);
  } catch {
    analytics = null;
  }

  const as_of_date = stats_loto.as_of_date || intersection.as_of_date || analytics?.newest || "—";

  return {
    target_date: stats_loto.target_date || intersection.target_date,
    as_of_date,
    api_base: base,
    analytics,
    stats_loto,
    stats_de,
    intersection,
    predictions,
  };
}

export async function fetchEngineBundle(settings?: ExtensionSettings): Promise<EngineBundle> {
  const s = settings || (await getSettings());
  const bases = apiBases(s);
  let lastError: Error | null = null;

  for (const base of bases) {
    try {
      const data = await fetchEngineFromBase(base);
      if (normalizeApiBase(base) !== normalizeApiBase(s.api_base_url)) {
        await saveSettings({ api_base_url: normalizeApiBase(base) });
      }
      return data;
    } catch (e) {
      lastError = e instanceof Error ? e : new Error(String(e));
    }
  }

  throw lastError || new Error("Không kết nối API — chạy: APP_PORT=18715 python run.py");
}
