import type { ExtensionSettings } from "../types/forum.js";
import { apiBases, apiFetch, normalizeApiBase } from "./api-base.js";
import { getSettings, saveSettings } from "./storage.js";

export interface ForumLotoRow {
  loto: string;
  score: number;
  votes?: number;
  users: string[];
  types: string[];
  reasons: string[];
}

export interface ExpertPerformance {
  hits: number;
  total: number;
  rate_pct: number;
  low_sample?: boolean;
}

export type ScoringMode = "weight" | "measured" | "blend";

export interface LiveExpertRow {
  user: string;
  pick_type: string;
  numbers: string[];
  weight: number;
  effective_weight?: number;
  performance?: ExpertPerformance | null;
  posted_at?: string;
  forum?: string;
  post_id?: string;
  thread_id?: string;
  thread_url?: string;
}

export interface DeChamLeader {
  user: string;
  cham: string[];
  weight?: number;
  effective_weight?: number;
}

export interface DanBoardRow {
  user: string;
  pick_type: string;
  size: string;
  count: number;
  weight: number;
  effective_weight?: number;
  performance?: ExpertPerformance | null;
  numbers: string[];
  posted_at?: string;
  forum?: string;
}

export interface DeByExpertRow {
  user: string;
  dan_size: string | null;
  dan_count: number;
  dan_preview: string[];
  de_cham: string[];
  de_dau: string[];
  de_tong: string[];
  btd: string[];
  btd_dau: string[];
  forum?: string | null;
  weight: number;
  effective_weight?: number;
  performance?: ExpertPerformance | null;
}

export interface ConsensusChamRow {
  cham: string;
  votes: number;
  users: string[];
}

export interface ConsensusStats {
  max_votes: number;
  strong_loto_count: number;
  bao_lo_overlap: number;
  bao_lo_overlap_pct: number;
  has_strong_consensus: boolean;
}

export interface ConsensusBlock {
  picks: {
    btl_lo: string | null;
    bao_lo_9: string[];
    xien_2: string[];
    de_top_4: string[];
  };
  loto_top10: ForumLotoRow[];
  de_cham: ConsensusChamRow[];
  stats?: ConsensusStats;
}

export interface RecommendationsResponse {
  target_date: string;
  source: "forum";
  scoring_mode?: ScoringMode;
  scoring_mode_label?: string;
  scoring_period?: string;
  scoring_period_label?: string;
  performance_period?: string;
  performance_period_label?: string;
  confidence: number;
  expert_count: number;
  has_forum_session: boolean;
  picks: {
    btl_lo: string | null;
    bao_lo_9: string[];
    xien_2: string[];
    de_top_4: string[];
  };
  consensus?: ConsensusBlock;
  de_cham_leaders: DeChamLeader[];
  dan_board: DanBoardRow[];
  de_by_expert?: DeByExpertRow[];
  forum_loto_top10: ForumLotoRow[];
  live_experts: LiveExpertRow[];
}

async function fetchFromBase(
  base: string,
  targetDate: string,
  scoringMode: ScoringMode,
): Promise<RecommendationsResponse> {
  const qs = new URLSearchParams({
    target_date: targetDate,
    scoring_mode: scoringMode,
  });
  const url = `${base}/forum/recommendations?${qs}`;
  const res = await apiFetch(url, { headers: { Accept: "application/json" } });
  if (res.error) throw new Error(res.error);
  if (res.status === 404) {
    throw new Error(`API ${base} thiếu /forum — restart: APP_PORT=18715 python run.py`);
  }
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${res.body.slice(0, 120)}`);
  }
  return JSON.parse(res.body) as RecommendationsResponse;
}

export async function fetchRecommendations(
  targetDate: string,
  settings?: ExtensionSettings,
  scoringMode: ScoringMode = "blend",
): Promise<RecommendationsResponse> {
  const s = settings || (await getSettings());
  const bases = apiBases(s);
  let lastError: Error | null = null;

  for (const base of bases) {
    try {
      const data = await fetchFromBase(base, targetDate, scoringMode);
      return data;
    } catch (e) {
      const err = e instanceof Error ? e : new Error(String(e));
      if (err.message.includes("thiếu /forum")) throw err;
      lastError = err;
    }
  }

  throw lastError || new Error("Không kết nối API — chạy: APP_PORT=18715 python run.py");
}

/** Persist working API base when fallback succeeded. */
export async function fetchRecommendationsAndSyncUrl(
  targetDate: string,
  settings?: ExtensionSettings,
  scoringMode: ScoringMode = "blend",
): Promise<RecommendationsResponse> {
  const s = settings || (await getSettings());
  const bases = apiBases(s);
  let lastError: Error | null = null;

  for (const base of bases) {
    try {
      const data = await fetchFromBase(base, targetDate, scoringMode);
      if (normalizeApiBase(base) !== normalizeApiBase(s.api_base_url)) {
        await saveSettings({ api_base_url: normalizeApiBase(base) });
      }
      return data;
    } catch (e) {
      const err = e instanceof Error ? e : new Error(String(e));
      if (err.message.includes("thiếu /forum")) throw err;
      lastError = err;
    }
  }

  throw lastError || new Error("Không kết nối API — chạy: APP_PORT=18715 python run.py");
}
