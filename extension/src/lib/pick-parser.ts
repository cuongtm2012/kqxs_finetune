import type { PostPicks } from "../types/forum.js";

function latestDaySection(text: string): string {
  // Support both:
  // - "Ngày 02.07.2026"
  // - "2/7" or "02/07/2026" (common shorthand in TL posts)
  const re1 = /ngày\s+\d{1,2}\s*[./-]\s*\d{1,2}\s*[./-]\s*\d{2,4}/gi;
  const re2 = /(?:^|\n)\s*\d{1,2}\s*[./-]\s*\d{1,2}(?:\s*[./-]\s*\d{2,4})?\b/gi;
  const matches = [...text.matchAll(re1), ...text.matchAll(re2)].sort(
    (a, b) => (a.index ?? 0) - (b.index ?? 0),
  );
  if (!matches.length) return text;
  const last = matches[matches.length - 1];
  // If there is only one date marker, still scope to it: treat post as multi-day log.
  return text.slice(last.index ?? 0).trim();
}

export function extractStl(text: string): string[] {
  // STL (song thủ lô) SHOULD be a single pair (2 numbers).
  // Monthly "nuôi khung" threads often contain many historical pairs; we only take the latest pair found.
  let lastPair: [string, string] | null = null;
  const patterns = [
    /STL[:\s]+(\d{2})\s*[,/\-]\s*(\d{2})/gi,
    // Common forum patterns:
    // "CẶP: 39-97", "CẶP: Lần 1: 39-97", "CẶP ... Lần 1 : 29,92"
    /CẶP[:\s]+(?:Lần\s*\d+\s*[:\s]+)?(\d{2})\s*[,/\-]\s*(\d{2})/gi,
    /cặp[:\s]+(?:Lần\s*\d+\s*[:\s]+)?(\d{2})\s*[,/\-]\s*(\d{2})/gi,
    /CẶP[\s\S]{0,40}?Lần\s*\d+\s*[:\s]+(\d{2})\s*[,/\-]\s*(\d{2})/gi,
    /cặp[\s\S]{0,40}?Lần\s*\d+\s*[:\s]+(\d{2})\s*[,/\-]\s*(\d{2})/gi,
  ];
  for (const pat of patterns) {
    let m: RegExpExecArray | null;
    while ((m = pat.exec(text)) !== null) {
      lastPair = [m[1], m[2]];
    }
  }
  if (!lastPair) return [];
  return [lastPair[0], lastPair[1]];
}

export function extractBtl(text: string): string[] {
  const nums = new Set<string>();
  const re = /BTL[:\s]*(\d{2})/gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) nums.add(m[1]);
  return [...nums].sort();
}

export function extractStdDe(text: string): string[] {
  // Preserve pair semantics: return tokens like "59-89" (not flattened numbers).
  // A user can "nuôi" multiple pairs in one post; keep all unique pairs in appearance order.
  const pairs: string[] = [];
  const re = /(?:STĐ|STD)\s*[:\s]+(\d{2})\s*[,/\-]\s*(\d{2})/gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    const token = `${m[1]}-${m[2]}`;
    if (!pairs.includes(token)) pairs.push(token);
  }
  return pairs;
}

export function extractBtdDe(text: string): string[] {
  const nums = new Set<string>();
  const re = /(?:BTĐ|BTD)\s*[:\s]+(\d{2})\b/gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) nums.add(m[1]);
  return [...nums].sort();
}

function parseDigitList(chunk: string): string[] {
  return [...chunk.matchAll(/\d/g)].map((x) => x[0]);
}

function parseBtdNumbers(chunk: string): string[] {
  const nums = new Set<string>();
  for (const m of chunk.matchAll(/[bB](\d{2})\b/g)) {
    nums.add(m[1]);
  }
  for (const m of chunk.matchAll(/(?:^|[\s,])(\d{2})\b/g)) {
    const v = m[1];
    if (Number(v) <= 99) nums.add(v);
  }
  return [...nums].sort();
}

function parseBtdDauDigits(chunk: string): string[] {
  const digits = new Set<string>();
  for (const m of chunk.matchAll(/[bB](\d+)/g)) {
    const rest = m[1];
    if (rest.length <= 2) {
      for (const d of rest) digits.add(d);
    } else {
      for (const d of rest) digits.add(d);
    }
  }
  return [...digits].sort();
}

/** Đề đặc biệt trong khu thảo luận: "Đề đặc biệt : b02,12" */
export function extractBtd(text: string): string[] {
  const nums = new Set<string>();
  const sectionRe = /đề\s*đặc\s*biệt\s*[:\s]+([\s\S]*?)(?=đề\s*đầu\s*đặc\s*biệt|;|$)/gi;
  for (const m of text.matchAll(sectionRe)) {
    for (const n of parseBtdNumbers(m[1])) nums.add(n);
  }
  for (const m of text.matchAll(/\bBTD\s*[:\s]+([\s\S]*?)(?=;|$|\n)/gi)) {
    for (const n of parseBtdNumbers(m[1])) nums.add(n);
    for (const n of m[1].matchAll(/\b(\d{2})\b/g)) {
      const v = n[1];
      if (Number(v) <= 99) nums.add(v);
    }
  }
  return [...nums].sort();
}

/** Đề đầu đặc biệt: "Đề đầu đặc biệt : b34" → 3, 4 */
export function extractBtdDau(text: string): string[] {
  const digits = new Set<string>();
  const sectionRe = /đề\s*đầu\s*đặc\s*biệt\s*[:\s]+([\s\S]*?)(?=;|$)/gi;
  for (const m of text.matchAll(sectionRe)) {
    for (const d of parseBtdDauDigits(m[1])) digits.add(d);
  }
  return [...digits].sort();
}

export function extractDeInfo(text: string): PostPicks["de"] {
  const result = { cham: [] as string[], tong: [] as string[], dau: [] as string[] };
  for (const m of text.matchAll(/chạm\s+([\d,\s]+?)(?:;|$|\s+tổng|\s+ăn)/gi)) {
    result.cham.push(...parseDigitList(m[1]));
  }
  for (const m of text.matchAll(/tổng\s+([\d,\s]+?)(?:;|$|\s+ăn|\s+chạm)/gi)) {
    result.tong.push(...parseDigitList(m[1]));
  }
  for (const m of text.matchAll(/đề\s*đầu\s+([\d,\s]+?)(?:\s+gút|;|$|\s+tổng|\s+chạm)/gi)) {
    if (/đặc\s*biệt/i.test(m[0])) continue;
    result.dau.push(...parseDigitList(m[1]));
  }
  if (!result.dau.length) {
    for (const m of text.matchAll(/đề\s*đầu\s+(\d)/gi)) {
      if (/đặc\s*biệt/i.test(m[0])) continue;
      result.dau.push(m[1]);
    }
  }
  // Lookingfor-style shorthand: "ĐB: CT1,6 (CT2,7; CT3,8) hạ C13458"
  for (const m of text.matchAll(/đb\s*:\s*([\s\S]*?)(?=bộ\s*:|20\s*em|1s:|3,4d:|$)/gi)) {
    const chunk = m[1];
    for (const ct of chunk.matchAll(/CT\s*([\d,\s]+)/gi)) {
      result.cham.push(...parseDigitList(ct[1]));
    }
    for (const h of chunk.matchAll(/(?:hạ\s*)?C\s*([0-9,\s]+)/gi)) {
      result.cham.push(...parseDigitList(h[1]));
    }
  }
  result.cham = [...new Set(result.cham)];
  result.tong = [...new Set(result.tong)];
  result.dau = [...new Set(result.dau)];
  return result;
}

export function inferDanPickType(
  count: number,
  threadTitle = "",
  text = "",
): "dan_40s" | "dan_36s" | "dan_64s" | "dan_de" {
  const blob = `${threadTitle} ${text}`.toLowerCase();
  if (/64\s*s|64s/.test(blob)) return "dan_64s";
  if (/36\s*s|36s/.test(blob)) return "dan_36s";
  if (/40\s*s|40s/.test(blob)) return "dan_40s";
  if (count >= 58) return "dan_64s";
  if (count >= 38) return "dan_40s";
  if (count >= 30) return "dan_36s";
  return "dan_de";
}

export function danSizeLabel(pickType: string): string {
  if (pickType === "dan_40s") return "40s";
  if (pickType === "dan_36s") return "36s";
  if (pickType === "dan_64s") return "64s";
  return "dàn";
}

export function extractDanDe(text: string): string[] {
  const nums = [...text.matchAll(/\b(\d{2})\b/g)].map((m) => m[1]);
  const valid = nums.filter((n) => Number(n) >= 0 && Number(n) <= 99);
  if (valid.length < 30) return [];
  return [...new Set(valid)];
}

export function extractMucLo(text: string): Record<number, string[]> {
  const result: Record<number, string[]> = {};
  let current: number | null = null;
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    const header = trimmed.match(/^Mức:\s*(\d+)\s*\(/i);
    if (header) {
      current = Number(header[1]);
      result[current] = [];
      continue;
    }
    if (current !== null && trimmed) {
      for (const n of trimmed.matchAll(/\b(\d{2})\b/g)) {
        const v = n[1];
        if (Number(v) >= 0 && Number(v) <= 99) result[current].push(v);
      }
    }
  }
  return result;
}

export function parsePicksFromContent(raw: string, threadTitle = ""): PostPicks {
  const scoped = latestDaySection(raw);
  const picks: PostPicks = {};
  const stl = extractStl(scoped);
  if (stl.length) picks.stl = stl;
  const btl = extractBtl(scoped);
  if (btl.length) picks.btl = btl;
  const stdDe = extractStdDe(scoped);
  if (stdDe.length) picks.std_de = stdDe;
  const btdDe = extractBtdDe(scoped);
  if (btdDe.length) picks.btd_de = btdDe;
  const de = extractDeInfo(scoped);
  if (de && (de.cham.length || de.tong.length || de.dau.length)) picks.de = de;
  const btd = extractBtd(scoped);
  if (btd.length) picks.btd = btd;
  const btdDau = extractBtdDau(scoped);
  if (btdDau.length) picks.btd_dau = btdDau;
  const dan = extractDanDe(scoped);
  if (dan.length) {
    picks.dan_de = dan;
    picks.dan_pick_type = inferDanPickType(dan.length, threadTitle, scoped);
  }
  const muc = extractMucLo(scoped);
  if (Object.keys(muc).length) picks.muc_lo = muc;
  return picks;
}

export function stripHtml(html: string): string {
  return html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}
