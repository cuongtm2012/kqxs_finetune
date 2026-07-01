import type { CollectSession } from "../types/forum.js";
import { getSettings, patchRuntimeStatus, saveSettings } from "./storage.js";

const FALLBACK_BASES = [
  "http://localhost:18715",
  "http://localhost:8081",
  "http://127.0.0.1:18715",
  "http://127.0.0.1:8081",
];

function apiBases(primary: string): string[] {
  const base = primary.replace(/\/$/, "");
  return [base, ...FALLBACK_BASES.filter((b) => b !== base)];
}

export async function pushSessionToApi(
  session: CollectSession,
  options: { force?: boolean } = {},
): Promise<boolean> {
  const settings = await getSettings();
  if (!options.force && !settings.auto_sync) return false;

  let lastError = "";
  for (const base of apiBases(settings.api_base_url)) {
    const url = `${base}/forum/picks`;
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(session),
      });
      if (res.status === 404) {
        lastError = `API ${base} thiếu /forum — restart: APP_PORT=18715 python run.py`;
        continue;
      }
      const ok = res.ok;
      if (!ok) {
        const text = await res.text();
        lastError = `HTTP ${res.status}: ${text.slice(0, 120)}`;
        continue;
      }
      if (base !== settings.api_base_url.replace(/\/$/, "")) {
        await saveSettings({ api_base_url: base });
      }
      await patchRuntimeStatus({
        last_sync_status: `OK ${new Date().toISOString()}`,
      });
      return true;
    } catch (e) {
      lastError = e instanceof Error ? e.message : String(e);
    }
  }
  await patchRuntimeStatus({ last_sync_status: `Error: ${lastError || "no API"}` });
  if (options.force && lastError) {
    throw new Error(lastError || "Không kết nối API — chạy: APP_PORT=18715 python run.py");
  }
  return false;
}

/** Sync when auto_sync is enabled (poll/finalize hooks). */
export async function syncSessionToApi(session: CollectSession): Promise<boolean> {
  return pushSessionToApi(session);
}
