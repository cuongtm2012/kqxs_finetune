import type { ExtensionSettings } from "../types/forum.js";
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
}

export interface LiveExpertRow {
  user: string;
  pick_type: string;
  numbers: string[];
  weight: number;
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
}

export interface DanBoardRow {
  user: string;
  pick_type: string;
  size: string;
  count: number;
  weight: number;
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

const FALLBACK_BASES = [
  "http://localhost:18715",
  "http://localhost:8081",
  "http://127.0.0.1:18715",
  "http://127.0.0.1:8081",
];

function apiBases(settings: ExtensionSettings): string[] {
  const primary = settings.api_base_url.replace(/\/$/, "");
  return [primary, ...FALLBACK_BASES.filter((b) => b !== primary)];
}

async function fetchFromBase(
  base: string,
  targetDate: string,
): Promise<RecommendationsResponse> {
  const url = `${base}/forum/recommendations?target_date=${encodeURIComponent(targetDate)}`;
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (res.status === 404) {
    throw new Error(`API ${base} thiếu /forum — restart: APP_PORT=18715 python run.py`);
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text.slice(0, 120)}`);
  }
  return res.json() as Promise<RecommendationsResponse>;
}

export async function fetchRecommendations(
  targetDate: string,
  settings?: ExtensionSettings,
): Promise<RecommendationsResponse> {
  const s = settings || (await getSettings());
  const bases = apiBases(s);
  let lastError: Error | null = null;

  for (const base of bases) {
    try {
      const data = await fetchFromBase(base, targetDate);
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
): Promise<RecommendationsResponse> {
  const s = settings || (await getSettings());
  const bases = apiBases(s);
  let lastError: Error | null = null;

  for (const base of bases) {
    try {
      const data = await fetchFromBase(base, targetDate);
      if (base !== s.api_base_url.replace(/\/$/, "")) {
        await saveSettings({ api_base_url: base });
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
