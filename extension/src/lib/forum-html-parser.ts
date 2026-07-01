import type { ForumKey, ForumPost } from "../types/forum.js";
import { parsePicksFromContent, stripHtml } from "./pick-parser.js";

export interface RawPostRow {
  post_id: string;
  user: string;
  posted_at_ms: number;
  raw_content: string;
}

export function extractPostsFromHtml(html: string): RawPostRow[] {
  const posts: RawPostRow[] = [];
  const blockRe =
    /<li[^>]*\bid="post-(\d+)"[^>]*>([\s\S]*?)<\/li>/gi;
  let block: RegExpExecArray | null;
  while ((block = blockRe.exec(html)) !== null) {
    const postId = block[1];
    const chunk = block[2];
    const user =
      chunk.match(/data-author="([^"]+)"/i)?.[1]?.trim() ||
      chunk.match(/class="username"[^>]*>([^<]+)</i)?.[1]?.trim() ||
      "";
    const rawTime = Number(chunk.match(/data-time="(\d+)"/i)?.[1] || "0");
    // XenForo 1.x = seconds; XenForo 2.x = milliseconds
    const timeMs = rawTime > 0 && rawTime < 1e11 ? rawTime * 1000 : rawTime || Date.now();
    const contentMatch = chunk.match(
      /<blockquote[^>]*class="messageText[^"]*"[^>]*>([\s\S]*?)<\/blockquote>/i,
    );
    if (!contentMatch) continue;
    const raw = stripHtml(contentMatch[1]);
    if (!user || raw.length < 15) continue;
    posts.push({
      post_id: postId,
      user,
      posted_at_ms: timeMs || Date.now(),
      raw_content: raw,
    });
  }

  if (posts.length === 0) {
    const fallback =
      /<a[^>]*class="username"[^>]*>([^<]+)<\/a>[\s\S]*?<blockquote[^>]*class="messageText[^"]*"[^>]*>([\s\S]*?)<\/blockquote>/gi;
    let m: RegExpExecArray | null;
    let idx = 0;
    while ((m = fallback.exec(html)) !== null) {
      idx += 1;
      const raw = stripHtml(m[2]);
      if (raw.length < 15) continue;
      posts.push({
        post_id: `fb-${idx}`,
        user: m[1].trim(),
        posted_at_ms: Date.now(),
        raw_content: raw,
      });
    }
  }
  return posts;
}

export function toForumPosts(
  rows: RawPostRow[],
  forum: ForumKey,
  threadSlug: string,
  windowStartMs: number,
  windowEndMs: number,
  threadTitle = "",
): ForumPost[] {
  return rows
    .filter((r) => r.posted_at_ms >= windowStartMs && r.posted_at_ms < windowEndMs)
    .map((r) => ({
      post_id: r.post_id,
      thread_id: threadSlug,
      forum,
      user: r.user,
      posted_at: new Date(r.posted_at_ms).toISOString(),
      posted_at_ms: r.posted_at_ms,
      raw_content: r.raw_content,
      picks: parsePicksFromContent(r.raw_content, threadTitle),
    }));
}

export function getLastPageFromHtml(html: string): number {
  const nav = html.match(/class="pageNav[^"]*"[\s\S]*?<\/nav>/i)?.[0] || html;
  const pages = [...nav.matchAll(/page-(\d+)/gi)].map((m) => Number(m[1]));
  if (pages.length) return Math.max(...pages);
  const last = nav.match(/<a[^>]*>(\d+)<\/a>\s*<\/li>\s*<\/ul>/i);
  if (last) return Number(last[1]);
  return 1;
}

export function extractThreadLinks(html: string): { url: string; title: string; slug: string }[] {
  const links: { url: string; title: string; slug: string }[] = [];
  const seen = new Set<string>();

  const re =
    /<a[^>]+href="(?:https?:\/\/[^"]*)?threads\/([^."?#/]+(?:\.[^"?#/]+)?)[^"]*"[^>]*>([^<]+)<\/a>/gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(html)) !== null) {
    const slug = m[1];
    if (seen.has(slug)) continue;
    const title = m[2].replace(/\s+/g, " ").trim();
    if (!title || title.length < 8) continue;
    if (/^(page-\d+|\d+)$/i.test(title)) continue;
    seen.add(slug);
    links.push({
      url: `https://forumketqua.net/threads/${slug}/`,
      title,
      slug,
    });
  }
  return links;
}

export function isLoggedInHtml(html: string): boolean {
  return /class="[^"]*\bLoggedIn\b/i.test(html);
}

export function isLoginPage(html: string): boolean {
  if (isLoggedInHtml(html)) return false;
  return (
    /class="[^"]*loginForm/i.test(html) ||
    (/\/login\/?"/i.test(html) && /name="login"/i.test(html))
  );
}

export function extractXfToken(html: string): string | null {
  const fromInput = html.match(/name="_xfToken"\s+value="([^"]+)"/i)?.[1];
  if (fromInput) return fromInput;

  const fromJs = html.match(/_csrfToken:\s*"([^"]+)"/i)?.[1];
  if (fromJs) return fromJs;

  const fromEmbed = html.match(/csrf=([A-Za-z0-9]+)/i)?.[1];
  if (fromEmbed) return fromEmbed;

  return null;
}
