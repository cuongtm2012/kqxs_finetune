import type { PostPicks } from "../types/forum.js";

export function extractStl(text: string): string[] {
  const nums = new Set<string>();
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
      nums.add(m[1]);
      nums.add(m[2]);
    }
  }
  return [...nums].sort();
}

export function extractBtl(text: string): string[] {
  const nums = new Set<string>();
  const re = /BTL[:\s]*(\d{2})/gi;
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
  const picks: PostPicks = {};
  const stl = extractStl(raw);
  if (stl.length) picks.stl = stl;
  const btl = extractBtl(raw);
  if (btl.length) picks.btl = btl;
  const de = extractDeInfo(raw);
  if (de && (de.cham.length || de.tong.length || de.dau.length)) picks.de = de;
  const btd = extractBtd(raw);
  if (btd.length) picks.btd = btd;
  const btdDau = extractBtdDau(raw);
  if (btdDau.length) picks.btd_dau = btdDau;
  const dan = extractDanDe(raw);
  if (dan.length) {
    picks.dan_de = dan;
    picks.dan_pick_type = inferDanPickType(dan.length, threadTitle, raw);
  }
  const muc = extractMucLo(raw);
  if (Object.keys(muc).length) picks.muc_lo = muc;
  return picks;
}

export function stripHtml(html: string): string {
  return html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}
