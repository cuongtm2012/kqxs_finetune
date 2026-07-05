import { runPollCycle, setupAlarms } from "../lib/collector.js";
import { ensureLoggedIn } from "../lib/forum-auth.js";
import { seedDefaultsOnInstall } from "../lib/storage.js";

function fetchTimeoutSignal(ms: number): AbortSignal {
  if (typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function") {
    return AbortSignal.timeout(ms);
  }
  const ctrl = new AbortController();
  setTimeout(() => ctrl.abort(), ms);
  return ctrl.signal;
}

async function handleApiFetch(message: {
  url: string;
  method?: string;
  headers?: Record<string, string>;
  body?: string;
  timeoutMs?: number;
}) {
  const timeoutMs = message.timeoutMs ?? 15_000;
  try {
    const res = await fetch(message.url, {
      method: message.method || "GET",
      headers: message.headers,
      body: message.body,
      signal: fetchTimeoutSignal(timeoutMs),
    });
    const body = await res.text();
    return { ok: res.ok, status: res.status, body };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { ok: false, status: 0, body: "", error: msg };
  }
}

chrome.runtime.onInstalled.addListener(async () => {
  await seedDefaultsOnInstall();
  await setupAlarms();
  await runPollCycle();
});

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === "rbk-poll") {
    await setupAlarms();
    await runPollCycle();
    return;
  }
  if (alarm.name === "rbk-rollover") {
    await setupAlarms();
    await runPollCycle({ force: true });
  }
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  (async () => {
    switch (message?.type) {
      case "POLL_NOW":
        return runPollCycle({ force: true });
      case "LOGIN":
        return { ok: await ensureLoggedIn() };
      case "SETUP_ALARMS":
        await setupAlarms();
        return { ok: true };
      case "API_FETCH":
        return handleApiFetch(message);
      default:
        return { error: "unknown" };
    }
  })()
    .then(sendResponse)
    .catch((e) => sendResponse({ error: e instanceof Error ? e.message : String(e) }));
  return true;
});

setupAlarms().catch(console.error);
