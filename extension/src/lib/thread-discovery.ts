import type { DiscoveredThread, ForumKey } from "../types/forum.js";
import { FORUMS } from "../types/forum.js";
import { extractThreadLinks } from "./forum-html-parser.js";
import { fetchForumHtml } from "./forum-auth.js";

/** 7 topic ghim đầu khu chăn nuôi — https://forumketqua.net/forums/chan-nuoi-xsmb.15/ */
export const CHAN_NUOI_PINNED_TOPICS = [
  { key: "btl_k5n", label: "BTL K5N", pattern: /BTL\s*K5N/i },
  { key: "stl_k2n", label: "STL K2N", pattern: /SONG THU L[ÔO]\s*KHUNG\s*2\s*NG[ÀA]Y|KHUNG\s*2\s*NG[ÀA]Y/i },
  { key: "btl_k3n", label: "BTL K3N", pattern: /BTL\s*K3N/i },
  { key: "dan_64s", label: "Dàn 64s", pattern: /64\s*S(?!\d)/i },
  { key: "stl_k3n", label: "STL K3N", pattern: /SONG THU L[ÔO]\s*KHUNG\s*3\s*NG[ÀA]Y|KHUNG\s*3\s*NG[ÀA]Y/i },
  { key: "dan_36s", label: "Dàn 36s", pattern: /36\s*S(?!\d)/i },
  { key: "dan_40s", label: "Dàn 40s", pattern: /40\s*S(?!\d)/i },
] as const;

function normalizeTitle(s: string): string {
  return s.normalize("NFC").replace(/\s+/g, " ").trim().toUpperCase();
}

function parseDateFromTitle(title: string): string | null {
  const m = title.match(/(\d{1,2})[/.](\d{1,2})[/.](\d{4})/);
  if (!m) return null;
  const d = Number(m[1]);
  const mo = Number(m[2]);
  const y = Number(m[3]);
  return `${y}-${String(mo).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

function monthTokens(targetDate: string): string[] {
  const [y, m] = targetDate.split("-").map(Number);
  return [
    `THÁNG ${m}/${y}`,
    `THÁNG ${m}`,
    `${m}/${y}`,
    `THANG ${m}/${y}`,
    String(y),
  ].map((t) => t.toUpperCase());
}

function isLockedTitle(title: string): boolean {
  return /ĐÃ KHÓA|ĐÃ KHOÁ|ĐÃ KHÓA/i.test(normalizeTitle(title));
}

function threadMonthScore(title: string, targetDate: string): number {
  const t = normalizeTitle(title);
  const tokens = monthTokens(targetDate);
  if (tokens.some((tok) => t.includes(tok))) return 20;
  const parsed = parseDateFromTitle(title);
  if (parsed) {
    const [y, m] = targetDate.split("-");
    if (parsed.startsWith(`${y}-${m}`)) return 15;
  }
  return 0;
}

const DAILY_PATTERNS: Record<"mo_bat" | "thao_luan", RegExp> = {
  mo_bat: /MỞ BÁT/i,
  thao_luan: /THẢO LUẬN.*NGÀY/i,
};

export async function discoverDailyThread(
  forum: "mo_bat" | "thao_luan",
  targetDate: string,
): Promise<DiscoveredThread | null> {
  const listingUrl = FORUMS[forum].listingUrl;
  for (const page of [1, 2]) {
    const url = page === 1 ? listingUrl : `${listingUrl}page-${page}`;
    const html = await fetchForumHtml(url);
    const links = extractThreadLinks(html);
    for (const link of links) {
      const title = normalizeTitle(link.title);
      if (!DAILY_PATTERNS[forum].test(title)) continue;
      const dateKey = parseDateFromTitle(title);
      if (dateKey === targetDate) {
        return { ...link, forum };
      }
    }
  }
  return null;
}

/**
 * Lấy đúng 7 topic ghim chăn nuôi (tháng hiện tại), ưu tiên topic mở — không lấy "Đã khóa" nếu có bản tháng mới.
 */
export async function discoverChanNuoiThreads(
  targetDate: string,
  _patterns?: string[],
): Promise<DiscoveredThread[]> {
  const html = await fetchForumHtml(FORUMS.chan_nuoi.listingUrl);
  const links = extractThreadLinks(html);

  const best = new Map<string, { thread: DiscoveredThread; score: number }>();

  for (const link of links) {
    const title = link.title;
    const norm = normalizeTitle(title);
    const locked = isLockedTitle(title);
    const monthScore = threadMonthScore(title, targetDate);

    for (const topic of CHAN_NUOI_PINNED_TOPICS) {
      if (!topic.pattern.test(norm)) continue;

      // BTL K3N vs K5N: pattern đã tách key
      let score = monthScore;
      if (locked) score -= 50;
      // Topic ghim thường nằm đầu listing — bonus nhẹ theo thứ tự
      const idx = links.findIndex((l) => l.slug === link.slug);
      if (idx >= 0 && idx < 12) score += 5 - Math.min(idx, 5);

      const prev = best.get(topic.key);
      if (
        !prev ||
        score > prev.score ||
        (score === prev.score && link.slug.localeCompare(prev.thread.slug) < 0)
      ) {
        best.set(topic.key, {
          thread: { ...link, forum: "chan_nuoi" as ForumKey },
          score,
        });
      }
    }
  }

  // Nếu thiếu topic (chưa có tháng mới), fallback bản khóa cùng loại
  for (const link of links) {
    const norm = normalizeTitle(link.title);
    for (const topic of CHAN_NUOI_PINNED_TOPICS) {
      if (best.has(topic.key)) continue;
      if (!topic.pattern.test(norm)) continue;
      best.set(topic.key, {
        thread: { ...link, forum: "chan_nuoi" as ForumKey },
        score: isLockedTitle(link.title) ? -10 : 0,
      });
    }
  }

  return CHAN_NUOI_PINNED_TOPICS.map((t) => best.get(t.key)?.thread).filter(
    (x): x is DiscoveredThread => Boolean(x),
  );
}

export async function discoverAllThreads(
  targetDate: string,
  pinnedPatterns?: string[],
): Promise<DiscoveredThread[]> {
  const [moBat, thaoLuan, chanNuoi] = await Promise.all([
    discoverDailyThread("mo_bat", targetDate),
    discoverDailyThread("thao_luan", targetDate),
    discoverChanNuoiThreads(targetDate, pinnedPatterns),
  ]);
  const out: DiscoveredThread[] = [];
  if (moBat) out.push(moBat);
  if (thaoLuan) out.push(thaoLuan);
  out.push(...chanNuoi);
  return out;
}
