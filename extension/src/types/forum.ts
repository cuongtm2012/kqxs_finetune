export type ForumKey = "mo_bat" | "thao_luan" | "chan_nuoi";

export type AuthStatus = "logged_in" | "not_logged_in" | "error" | "checking";

export interface ForumAuth {
  username: string;
  password: string;
  remember: boolean;
  login_url: string;
}

export interface PostPicks {
  stl?: string[];
  btl?: string[];
  /** Song thủ đề: "STĐ: 59,89" */
  std_de?: string[];
  /** Bạch thủ đề: "BTĐ: 89" */
  btd_de?: string[];
  de?: { cham: string[]; tong: string[]; dau: string[] };
  /** Đề đặc biệt (thảo luận): b02, b12 → 02, 12 */
  btd?: string[];
  /** Đề đầu đặc biệt: b34 → 3, 4 */
  btd_dau?: string[];
  dan_de?: string[];
  dan_pick_type?: "dan_40s" | "dan_36s" | "dan_64s" | "dan_de";
  /** Casual đề list: "4 số : 14,41,78,87" */
  de_list?: string[];
  muc_lo?: Record<number, string[]>;
}

export interface ForumPost {
  post_id: string;
  thread_id: string;
  forum: ForumKey;
  user: string;
  posted_at: string;
  posted_at_ms: number;
  raw_content: string;
  picks: PostPicks;
}

export interface ThreadState {
  url: string;
  title: string;
  thread_slug: string;
  last_post_time: number;
  last_page_fetched: number;
  last_fetch_at?: number;
  /** Backfill pagination: lowest page fetched so far (counting down from last page). */
  lowest_page_fetched?: number;
  /** True when we've fetched enough pages to cover windowStartMs. */
  backfill_complete?: boolean;
  /** Cumulative pages fetched (audit). */
  pages_fetched_total?: number;
}

export interface ForumDaySummary {
  date: string;
  weekday: string;
  target_date: string;
  collected_at?: string;
  forums: {
    mo_bat?: { thread_url: string; post_count: number };
    thao_luan?: { thread_url: string; post_count: number };
    chan_nuoi?: { threads: { url: string; title: string }[]; post_count: number };
  };
  stl_k2n_users: Record<string, { stl: string[]; raw?: string }>;
  btl_k3n_users: Record<string, { btl: string[]; raw?: string }>;
  daily_users: Record<string, { stl: string[]; btl: string[]; de: PostPicks["de"] }>;
  muc_lo: Record<number, string[]>;
  dan_de: string[];
  dan_board: {
    user: string;
    pick_type: string;
    size: string;
    count: number;
    numbers: string[];
  }[];
  de_cham_leaders: { user: string; cham: string[] }[];
  stl_frequency: Record<string, { count: number; users: string[] }>;
  btl_frequency: Record<string, { count: number; users: string[] }>;
  all_posts?: ForumPost[];
}

export interface CollectSession {
  target_date: string;
  window_start: string;
  window_end: string;
  finalized_at?: string;
  /** Finalized while daily-thread backfill was incomplete. */
  coverage_warning?: boolean;
  /** Khóa danh sách thread sau lần discover đầu — tránh poll nhậy topic. */
  discovered_threads?: DiscoveredThread[];
  threads: Record<string, ThreadState>;
  posts: Record<string, ForumPost>;
  summary: ForumDaySummary;
}

export interface ExtensionSettings {
  timezone: string;
  poll_interval_active_min: number;
  poll_interval_idle_min: number;
  api_base_url: string;
  auto_sync: boolean;
  target_users: string[];
  pinned_chan_nuoi_patterns: string[];
}

export interface RuntimeStatus {
  auth_status: AuthStatus;
  last_login_at?: string;
  last_poll_at?: string;
  last_error?: string;
  last_sync_status?: string;
  last_poll_status?: string;
  target_date: string;
  collect_status: "idle" | "collecting" | "backfilling" | "finalized" | "sunday_skip" | "waiting_thread";
  post_count: number;
  new_posts_last_poll: number;
}

export interface DiscoveredThread {
  url: string;
  title: string;
  slug: string;
  forum: ForumKey;
}

export const STORAGE_KEYS = {
  settings: "rbk_settings",
  forumAuth: "forum_auth",
  runtime: "rbk_runtime",
  sessionPrefix: "session:",
} as const;

export const DEFAULT_SETTINGS: ExtensionSettings = {
  timezone: "Asia/Ho_Chi_Minh",
  poll_interval_active_min: 5,
  poll_interval_idle_min: 30,
  api_base_url: "http://127.0.0.1:18715",
  auto_sync: false,
  target_users: [
    "LangThang1977", "Haiphong27", "T98", "TieuToanPhong",
    "nhcsxh", "gimala", "HoangTin333", "Lookingfor",
    "dogati", "quedau1981", "emvatoi213", "BaMinhBeo",
    "Nhu_Y", "Kubi247", "113",
  ],
  pinned_chan_nuoi_patterns: [
    "BTL K5N",
    "SONG THU LO KHUNG 2 NGAY",
    "BTL K3N",
    "64S",
    "SONG THU LO KHUNG 3 NGAY",
    "36S KHUNG",
    "40S KHUNG",
  ],
};

export const DEFAULT_FORUM_AUTH: ForumAuth = {
  username: "kinosa89",
  password: "hanchechat",
  remember: true,
  login_url: "https://forumketqua.net/login/",
};

export const BASE_URL = "https://forumketqua.net";

export const FORUMS: Record<ForumKey, { name: string; listingUrl: string }> = {
  mo_bat: {
    name: "Khu mở bát",
    listingUrl: `${BASE_URL}/forums/khu-mo-bat.13/`,
  },
  thao_luan: {
    name: "Thảo luận, dự đoán XSMB",
    listingUrl: `${BASE_URL}/forums/du-doan-xsmb/`,
  },
  chan_nuoi: {
    name: "Chăn nuôi XSMB",
    listingUrl: `${BASE_URL}/forums/chan-nuoi-xsmb.15/`,
  },
};

export const WEEKDAYS_VI = [
  "Chủ Nhật", "Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy",
];
