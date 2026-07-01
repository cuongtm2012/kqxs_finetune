const COLLECT_START_H = 18;
const COLLECT_START_M = 30;
const COLLECT_END_H = 18;
const COLLECT_END_M = 0;
const DRAW_H = 18;
const DRAW_M = 15;

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
  const drawMs = wallToUtcMs(y, m, d, DRAW_H, DRAW_M, timeZone);
  return now.getTime() >= drawMs;
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
