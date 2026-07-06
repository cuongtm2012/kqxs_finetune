import type { PostPicks } from "../types/forum.js";

/** Decode HTML entities from stripHtml (e.g. &gt; → >). */
export function normalizeForumText(text: string): string {
  return text
    .replace(/&gt;/gi, ">")
    .replace(/&lt;/gi, "<")
    .replace(/&amp;/gi, "&")
    .replace(/&nbsp;/gi, " ")
    .replace(/\u00a0/g, " ");
}

/** Remove XenForo quote/reply blocks — avoids parsing quoted picks from other users. */
export function stripQuoteBlocks(text: string): string {
  let out = text;
  // "User nói: ↑ ... Click to expand"
  out = out.replace(
    /[\w.\-_]+ nói:\s*(?:↑|&uarr;)?[\s\S]*?(?:Click to expand|$)/gi,
    " ",
  );
  // HTML quote blocks if any raw tags remain
  out = out.replace(/<blockquote[^>]*class="[^"]*quote[^"]*"[^>]*>[\s\S]*?<\/blockquote>/gi, " ");
  return out.replace(/\s+/g, " ").trim();
}

function dayMarkers(text: string): Array<{ day: number; month: number; year?: number; start: number }> {
  const out: Array<{ day: number; month: number; year?: number; start: number }> = [];
  const seen = new Set<number>();

  const add = (day: number, month: number, year: number | undefined, start: number) => {
    if (day < 1 || day > 31 || month < 1 || month > 12) return;
    if (seen.has(start)) return;
    seen.add(start);
    out.push({ day, month, year, start });
  };

  let m: RegExpExecArray | null;
  const predRe = /dự\s*đoán\s+(?:xsmb\s+)?(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{2,4})\b/gi;
  while ((m = predRe.exec(text)) !== null) {
    let year = Number(m[3]);
    if (year < 100) year += 2000;
    add(Number(m[1]), Number(m[2]), year, m.index + m[0].search(/\d/));
  }

  const pat = /(?:^|\s)(?:ngày\s+)?(\d{1,2})\s*[./-]\s*(\d{1,2})(?:\s*[./-]\s*(\d{2,4}))?\b/gi;
  while ((m = pat.exec(text)) !== null) {
    let year: number | undefined;
    if (m[3]) {
      year = Number(m[3]);
      if (year < 100) year += 2000;
    }
    add(Number(m[1]), Number(m[2]), year, m.index + m[0].search(/\d/));
  }
  out.sort((a, b) => a.start - b.start);
  return out;
}

export function daySectionForTargetDate(text: string, targetDate: string): string | null {
  const [y, mo, d] = targetDate.split("-").map(Number);
  const markers = dayMarkers(text);
  if (!markers.length) return null;
  for (let i = 0; i < markers.length; i++) {
    const mk = markers[i];
    if (mk.day !== d || mk.month !== mo) continue;
    if (mk.year !== undefined && mk.year !== y) continue;
    const end = i + 1 < markers.length ? markers[i + 1].start : text.length;
    return text.slice(mk.start, end).trim();
  }
  return null;
}

function latestDaySection(text: string): string {
  // Support:
  // - "Ngày 02.07.2026" / "Ngày 05/7" / "Ngày 05/7/2026"
  // - "2/7" or "02/07/2026" inline (one-line cumulative thảo luận posts)
  const markers = dayMarkers(text);
  if (!markers.length) return text;
  return text.slice(markers[markers.length - 1].start).trim();
}

export function extractStl(text: string): string[] {
  // STL (song thủ lô) SHOULD be a single pair (2 numbers).
  // Monthly "nuôi khung" threads often contain many historical pairs; we only take the latest pair found.
  let lastPair: [string, string] | null = null;
  const patterns = [
    /STL[:\s]+(\d{2})\s*[,/.\-]\s*(\d{2})/gi,
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
  // Event / thống kê posts often log multiple days; take numbers from the last BTL line only.
  const lines = text.split(/\n/);
  let lastBtlLine = "";
  for (const line of lines) {
    if (/BTL/i.test(line)) lastBtlLine = line;
  }
  const chunk = lastBtlLine || text;
  const nums = new Set<string>();
  for (const m of chunk.matchAll(/BTL[:\s]+([\d\s,/.\-]+)/gi)) {
    for (const n of m[1].matchAll(/\b(\d{2})\b/g)) {
      if (Number(n[1]) <= 99) nums.add(n[1]);
    }
  }
  if (!nums.size) {
    const re = /BTL[:\s]*(\d{2})/gi;
    let m: RegExpExecArray | null;
    while ((m = re.exec(chunk)) !== null) nums.add(m[1]);
  }
  return [...nums].sort();
}

function btlNumFromLanSection(section: string): string | null {
  const m = section.match(/(?:CHĂN\s+)?BTL\s*(\d{2})\b|chăn\s*(\d{2})\b/i);
  if (!m) return null;
  return m[1] || m[2];
}

export function splitLanSections(text: string): Array<{ lanNo: number; section: string }> {
  const parts = normalizeForumText(text).split(/(?=(?:Lần|LẦN)\s*\d+\s*(?::|BTL|CHĂN)|L\d+\s*:)/i);
  const out: Array<{ lanNo: number; section: string }> = [];
  for (const part of parts) {
    const p = part.trim();
    if (!p) continue;
    let m = p.match(/^(?:Lần|LẦN)\s*(\d+)\s*:\s*([\s\S]*)$/i);
    if (m) {
      out.push({ lanNo: Number(m[1]), section: m[2].trim() });
      continue;
    }
    m = p.match(/^(?:Lần|LẦN)\s*(\d+)\s+([\s\S]*)$/i);
    if (m) {
      out.push({ lanNo: Number(m[1]), section: m[2].trim() });
      continue;
    }
    m = p.match(/^L(\d+)\s*:\s*([\s\S]*)$/i);
    if (m) out.push({ lanNo: Number(m[1]), section: m[2].trim() });
  }
  return out;
}

function parseLanDayRange(
  fragment: string,
  defaultYear: number,
  defaultMonth: number,
): { year: number; month: number; d0: number; d1: number } | null {
  const frag = normalizeForumText(fragment);

  const valid = (yr: number, mo: number, d0: number, d1: number) => {
    if (d0 < 1 || d1 < 1 || d0 > 31 || d1 > 31) return null;
    return { year: yr, month: mo, d0, d1 };
  };

  let m = frag.match(
    /(?:từ|tu)\s*(\d{1,2})\s*\/\s*(\d{1,2})\s*(?:->|[-→>]+)\s*(\d{1,2})\s*\/\s*(\d{1,2})\b/i,
  );
  if (m) {
    const d0 = Number(m[1]);
    const mo = Number(m[2]);
    const d1 = Number(m[3]);
    const mo2 = Number(m[4]);
    if (mo === mo2) {
      const got = valid(defaultYear, mo, d0, d1);
      if (got) return got;
    }
  }

  m = frag.match(/(?:từ|tu)\s*(\d{1,2})\s*[>→\-]+\s*(\d{1,2})\b/i);
  if (m) {
    const got = valid(defaultYear, defaultMonth, Number(m[1]), Number(m[2]));
    if (got) return got;
  }

  m = frag.match(/(?:từ|tu)\s*(\d{1,2})\s*-\s*(\d{1,2})\b/i);
  if (m) {
    const got = valid(defaultYear, defaultMonth, Number(m[1]), Number(m[2]));
    if (got) return got;
  }

  const patterns: Array<{ re: RegExp; hasMonth: boolean }> = [
    { re: /(?:từ|tu)\s*(\d{1,2})\s*[>→\-]\s*(\d{1,2})\s*\/\s*(\d{1,2})/i, hasMonth: true },
    { re: /\(\s*(?:từ|tu)?\s*(\d{1,2})\s*[>→\-]\s*(\d{1,2})\s*\/\s*(\d{1,2})\s*\)/i, hasMonth: true },
    { re: /(?:từ|tu)\s*(\d{1,2})\s*-\s*(\d{1,2})\s*\/\s*(\d{1,2})/i, hasMonth: true },
    { re: /\(\s*(\d{1,2})\s*-\s*(\d{1,2})\s*\/\s*(\d{1,2})\s*\)/i, hasMonth: true },
    { re: /(\d{1,2})\s*-\s*(\d{1,2})\s*\/\s*(\d{1,2})/i, hasMonth: true },
    { re: /\(\s*(\d{1,2})\s*-\s*(\d{1,2})\s*\)/i, hasMonth: false },
  ];
  for (const { re, hasMonth } of patterns) {
    const hit = frag.match(re);
    if (!hit) continue;
    const d0 = Number(hit[1]);
    const d1 = Number(hit[2]);
    const mo = hasMonth ? Number(hit[3]) : defaultMonth;
    const got = valid(defaultYear, mo, d0, d1);
    if (got) return got;
  }
  return null;
}

/** Chăn nuôi BTL K3N — one BTL per Lần khung. null = not Lần format. */
export function extractBtlForTargetDate(
  text: string,
  targetDate: string,
): string[] | null {
  const sections = splitLanSections(text);
  if (!sections.length) return null;
  if (!sections.some((s) => btlNumFromLanSection(s.section))) return null;

  const [y, m, d] = targetDate.split("-").map(Number);
  const cur = Date.UTC(y, m - 1, d);
  let best: { lanNo: number; num: string } | null = null;

  for (const { lanNo, section } of sections) {
    const num = btlNumFromLanSection(section);
    if (!num) continue;
    const dr = parseLanDayRange(section, y, m);
    if (!dr || dr.month !== m || dr.year !== y) continue;
    const start = Date.UTC(dr.year, dr.month - 1, dr.d0);
    const end = Date.UTC(dr.year, dr.month - 1, dr.d1);
    if (cur < start || cur > end) continue;
    if (!best || lanNo >= best.lanNo) best = { lanNo, num };
  }
  return best ? [best.num] : [];
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

export function extractDeList(text: string): string[] {
  const nums = new Set<string>();
  for (const m of text.matchAll(/4\s*số\s*:\s*([0-9,\s]+)/gi)) {
    for (const n of m[1].matchAll(/\b(\d{2})\b/g)) {
      if (Number(n[1]) <= 99) nums.add(n[1]);
    }
  }
  return [...nums].sort();
}

export function extractDe1So(text: string): string[] {
  const nums = new Set<string>();
  for (const m of text.matchAll(/1\s*số\s*:\s*(\d{2})\b/gi)) {
    nums.add(m[1]);
  }
  return [...nums].sort();
}

function danExtractChunk(text: string): string {
  m = text.match(/(?:dàn|dan)\s*(?:đề|de)(?:\s+\d+\s*s(?:ố)?)?\s*:\s*/i);
  if (m && m.index !== undefined) return text.slice(m.index + m[0].length);
  m = text.match(/(?:dàn|dan)\s*(?:đề|de)(?:\s+\d+\s*s(?:ố)?)\s+/i);
  if (m && m.index !== undefined) return text.slice(m.index + m[0].length);
  m = text.match(/(?:dàn|dan)\s*(?:đề|de)[^\n]*/i);
  if (m && m.index !== undefined) return text.slice(m.index + m[0].length);
  return text
    .split("\n")
    .filter((line) => {
      const s = line.trim();
      if (/^\d{1,2}\s*[./-]\s*\d/.test(s)) return false;
      if (/\b(?:BTL|STL)\b/i.test(s)) return false;
      return true;
    })
    .join("\n");
}

export function extractDanDe(text: string): string[] {
  const chunk = danExtractChunk(text);
  const nums = [...chunk.matchAll(/\b(\d{2})\b/g)].map((m) => m[1]);
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

export function parsePicksFromContent(
  raw: string,
  threadTitle = "",
  targetDate = "",
): PostPicks {
  const stripped = stripQuoteBlocks(normalizeForumText(raw));
  if (stripped.length < 8 && !/\b(?:BTL|STL|Btl|Stl)\b/i.test(stripped)) return {};
  const scoped = targetDate
    ? (daySectionForTargetDate(stripped, targetDate) || latestDaySection(stripped))
    : latestDaySection(stripped);
  const picks: PostPicks = {};
  const stl = extractStl(scoped);
  if (stl.length) picks.stl = stl;
  let btl: string[] | null = null;
  if (targetDate) {
    btl = extractBtlForTargetDate(stripped, targetDate);
  }
  if (!btl?.length) {
    btl = extractBtl(scoped);
  }
  if (btl.length) picks.btl = btl;
  const stdDe = extractStdDe(scoped);
  if (stdDe.length) picks.std_de = stdDe;
  let btdDe = extractBtdDe(scoped);
  const de1 = extractDe1So(scoped);
  if (de1.length) {
    btdDe = [...new Set([...btdDe, ...de1])].sort();
  }
  if (btdDe.length) picks.btd_de = btdDe;
  const de = extractDeInfo(scoped);
  if (de && (de.cham.length || de.tong.length || de.dau.length)) picks.de = de;
  const btd = extractBtd(scoped);
  if (btd.length) picks.btd = btd;
  const btdDau = extractBtdDau(scoped);
  if (btdDau.length) picks.btd_dau = btdDau;
  const deList = extractDeList(scoped);
  if (deList.length) picks.de_list = deList;
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
