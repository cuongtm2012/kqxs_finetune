const COLLECT_START_H = 18;
const COLLECT_START_M = 30;
const COLLECT_END_H = 18;
const COLLECT_END_M = 0;
/** Kết quả XSMB thường có sau 18:30 — finalize session ngày D và chuyển sang thu thập D+1 */
const FINALIZE_H = COLLECT_START_H;
const FINALIZE_M = COLLECT_START_M;

function partsInTz(date: Date, timeZone: string) {
  const fmt = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  const parts = Object.fromEntries(
    fmt.formatToParts(date).map((p) => [p.type, p.value]),
  );
  return {
    year: Number(parts.year),
    month: Number(parts.month),
    day: Number(parts.day),
    hour: Number(parts.hour),
    minute: Number(parts.minute),
  };
}

export function dateKey(y: number, m: number, d: number): string {
  return `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

export function parseDateKey(key: string): Date {
  const [y, m, d] = key.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

function addDays(y: number, m: number, d: number, delta: number) {
  const dt = new Date(Date.UTC(y, m - 1, d));
  dt.setUTCDate(dt.getUTCDate() + delta);
  return { year: dt.getUTCFullYear(), month: dt.getUTCMonth() + 1, day: dt.getUTCDate() };
}

export function getCalendarDate(now = new Date(), timeZone = "Asia/Ho_Chi_Minh"): string {
  const p = partsInTz(now, timeZone);
  return dateKey(p.year, p.month, p.day);
}

/** Ngày quay vừa xong để xem kết quả: trước 18:31 → hôm qua, từ 18:31 → hôm nay. */
export function getLatestDrawScoreDate(now = new Date(), timeZone = "Asia/Ho_Chi_Minh"): string {
  const p = partsInTz(now, timeZone);
  const afterResult = p.hour > 18 || (p.hour === 18 && p.minute >= 31);
  if (afterResult) {
    return dateKey(p.year, p.month, p.day);
  }
  const prev = addDays(p.year, p.month, p.day, -1);
  return dateKey(prev.year, prev.month, prev.day);
}

export function getTargetDate(now = new Date(), timeZone = "Asia/Ho_Chi_Minh"): string {
  const p = partsInTz(now, timeZone);
  const afterStart =
    p.hour > COLLECT_START_H ||
    (p.hour === COLLECT_START_H && p.minute >= COLLECT_START_M);
  if (afterStart) {
    const next = addDays(p.year, p.month, p.day, 1);
    return dateKey(next.year, next.month, next.day);
  }
  return dateKey(p.year, p.month, p.day);
}

export function isSunday(dateKeyStr: string): boolean {
  const d = parseDateKey(dateKeyStr);
  return d.getUTCDay() === 0;
}

export function getCollectWindow(targetDate: string, timeZone = "Asia/Ho_Chi_Minh") {
  const [y, m, d] = targetDate.split("-").map(Number);
  const prev = addDays(y, m, d, -1);
  const startLabel = `${dateKey(prev.year, prev.month, prev.day)}T${String(COLLECT_START_H).padStart(2, "0")}:${String(COLLECT_START_M).padStart(2, "0")}:00`;
  const endLabel = `${targetDate}T${String(COLLECT_END_H).padStart(2, "0")}:${String(COLLECT_END_M).padStart(2, "0")}:00`;
  return { window_start: startLabel, window_end: endLabel, timeZone };
}

function wallToUtcMs(
  y: number, m: number, d: number, h: number, min: number, timeZone: string,
): number {
  const guess = new Date(Date.UTC(y, m - 1, d, h, min, 0));
  const fmt = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
    hour12: false,
  });
  for (let i = 0; i < 3; i++) {
    const parts = Object.fromEntries(fmt.formatToParts(guess).map((p) => [p.type, p.value]));
    const gotH = Number(parts.hour);
    const gotM = Number(parts.minute);
    const diffMin = (h * 60 + min) - (gotH * 60 + gotM);
    if (diffMin === 0) break;
    guess.setTime(guess.getTime() + diffMin * 60_000);
  }
  return guess.getTime();
}

export function isInCollectWindow(
  now = new Date(),
  targetDate = getTargetDate(now),
  timeZone = "Asia/Ho_Chi_Minh",
): boolean {
  const [y, m, d] = targetDate.split("-").map(Number);
  const prev = addDays(y, m, d, -1);
  const startMs = wallToUtcMs(prev.year, prev.month, prev.day, COLLECT_START_H, COLLECT_START_M, timeZone);
  const endMs = wallToUtcMs(y, m, d, COLLECT_END_H, COLLECT_END_M, timeZone);
  const nowMs = now.getTime();
  return nowMs >= startMs && nowMs < endMs;
}

export function shouldFinalize(
  now = new Date(),
  targetDate = getTargetDate(now),
  timeZone = "Asia/Ho_Chi_Minh",
): boolean {
  const [y, m, d] = targetDate.split("-").map(Number);
  const finalizeMs = wallToUtcMs(y, m, d, FINALIZE_H, FINALIZE_M, timeZone);
  return now.getTime() >= finalizeMs;
}

/** 30 minutes after finalize — allow closing session even if backfill incomplete. */
export const BACKFILL_FINALIZE_GRACE_MS = 30 * 60 * 1000;

export function getFinalizeGraceEndMs(
  targetDate: string,
  timeZone = "Asia/Ho_Chi_Minh",
): number {
  const [y, m, d] = targetDate.split("-").map(Number);
  return wallToUtcMs(y, m, d, FINALIZE_H, FINALIZE_M, timeZone) + BACKFILL_FINALIZE_GRACE_MS;
}

export function isPastFinalizeGrace(
  now = new Date(),
  targetDate = getTargetDate(now),
  timeZone = "Asia/Ho_Chi_Minh",
): boolean {
  return now.getTime() >= getFinalizeGraceEndMs(targetDate, timeZone);
}

/** Thời điểm rollover tiếp theo (18:30 ICT) — chuyển sang target_date mới */
export function getNextRolloverMs(now = new Date(), timeZone = "Asia/Ho_Chi_Minh"): number {
  const p = partsInTz(now, timeZone);
  const passedCutoff =
    p.hour > COLLECT_START_H || (p.hour === COLLECT_START_H && p.minute >= COLLECT_START_M);
  let { year: y, month: m, day: d } = p;
  if (passedCutoff) {
    const next = addDays(y, m, d, 1);
    y = next.year;
    m = next.month;
    d = next.day;
  }
  return wallToUtcMs(y, m, d, COLLECT_START_H, COLLECT_START_M, timeZone);
}

/** Sau 18:31 ICT — KQXS thường đã có, có thể chấm tự động. */
export function isAfterDrawSettlement(now = new Date(), timeZone = "Asia/Ho_Chi_Minh"): boolean {
  const p = partsInTz(now, timeZone);
  return p.hour > 18 || (p.hour === 18 && p.minute >= 31);
}

export function isAfterResultCutoff(now = new Date(), timeZone = "Asia/Ho_Chi_Minh"): boolean {
  const p = partsInTz(now, timeZone);
  return p.hour > COLLECT_START_H || (p.hour === COLLECT_START_H && p.minute >= COLLECT_START_M);
}

export function getWindowBoundsMs(
  targetDate: string,
  timeZone = "Asia/Ho_Chi_Minh",
): { startMs: number; endMs: number } {
  const [y, m, d] = targetDate.split("-").map(Number);
  const prev = addDays(y, m, d, -1);
  return {
    startMs: wallToUtcMs(prev.year, prev.month, prev.day, COLLECT_START_H, COLLECT_START_M, timeZone),
    endMs: wallToUtcMs(y, m, d, COLLECT_END_H, COLLECT_END_M, timeZone),
  };
}

export function weekdayVi(dateKeyStr: string): string {
  const d = parseDateKey(dateKeyStr);
  return ["Chủ Nhật", "Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy"][d.getUTCDay()];
}
