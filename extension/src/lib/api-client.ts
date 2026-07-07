import type { CollectSession } from "../types/forum.js";
import { apiBases, apiFetch, normalizeApiBase } from "./api-base.js";
import { getSettings, patchRuntimeStatus, saveSettings } from "./storage.js";

export async function pushSessionToApi(
  session: CollectSession,
  options: { force?: boolean } = {},
): Promise<boolean> {
  const settings = await getSettings();
  if (!options.force && !settings.auto_sync) return false;

  const postCount = Object.keys(session.posts || {}).length;
  if (postCount === 0) {
    await patchRuntimeStatus({
      last_sync_status: "Skipped empty session (0 posts)",
    });
    return false;
  }

  let lastError = "";
  for (const base of apiBases(settings)) {
    const url = `${base}/forum/picks`;
    try {
      const res = await apiFetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(session),
        timeoutMs: 120_000,
      });
      if (res.error) {
        lastError = res.error;
        continue;
      }
      if (res.status === 404) {
        lastError = `API ${base} thiếu /forum — restart: APP_PORT=18715 python run.py`;
        continue;
      }
      if (!res.ok) {
        lastError = `HTTP ${res.status}: ${res.body.slice(0, 120)}`;
        continue;
      }
      if (normalizeApiBase(base) !== normalizeApiBase(settings.api_base_url)) {
        await saveSettings({ api_base_url: normalizeApiBase(base) });
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
