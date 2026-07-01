import { runPollCycle, setupAlarms } from "../lib/collector.js";
import { ensureLoggedIn } from "../lib/forum-auth.js";
import { seedDefaultsOnInstall } from "../lib/storage.js";

chrome.runtime.onInstalled.addListener(async () => {
  await seedDefaultsOnInstall();
  await setupAlarms();
  await runPollCycle();
});

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === "rbk-poll") {
    await setupAlarms();
    await runPollCycle();
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
      default:
        return { error: "unknown" };
    }
  })()
    .then(sendResponse)
    .catch((e) => sendResponse({ error: e instanceof Error ? e.message : String(e) }));
  return true;
});

setupAlarms().catch(console.error);
