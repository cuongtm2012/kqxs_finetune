import type { ForumAuth } from "../types/forum.js";
import { BASE_URL } from "../types/forum.js";

export async function findForumTabIds(): Promise<number[]> {
  const tabs = await chrome.tabs.query({ url: ["https://forumketqua.net/*"] });
  return tabs.map((t) => t.id).filter((id): id is number => id !== undefined);
}

export async function loginInForumTab(auth: ForumAuth): Promise<boolean> {
  const tabIds = await findForumTabIds();
  if (tabIds.length === 0) return false;

  const tabId = tabIds[0];
  const sendLogin = async (): Promise<{ ok?: boolean } | undefined> => {
    try {
      return await chrome.tabs.sendMessage(tabId, { type: "LOGIN_IN_TAB", auth });
    } catch {
      try {
        await chrome.scripting.executeScript({
          target: { tabId },
          files: ["content.js"],
        });
        return await chrome.tabs.sendMessage(tabId, { type: "LOGIN_IN_TAB", auth });
      } catch {
        return undefined;
      }
    }
  };

  const result = await sendLogin();
  return result?.ok === true;
}

export async function syncForumTabUi(): Promise<void> {
  const tabIds = await findForumTabIds();
  for (const tabId of tabIds) {
    try {
      await chrome.tabs.sendMessage(tabId, { type: "SYNC_LOGIN_UI" });
    } catch {
      try {
        await chrome.tabs.reload(tabId);
      } catch {
        /* tab closed */
      }
    }
  }
}

export async function openForumTab(url = `${BASE_URL}/forums/xo-so-mien-bac/`): Promise<void> {
  const existing = await findForumTabIds();
  if (existing.length > 0) {
    await chrome.tabs.reload(existing[0]);
    return;
  }
  await chrome.tabs.create({ url });
}

function waitForTabComplete(tabId: number, timeoutMs = 12_000): Promise<void> {
  return new Promise((resolve) => {
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      chrome.tabs.onUpdated.removeListener(onUpdated);
      resolve();
    };
    const onUpdated = (id: number, info: chrome.tabs.TabChangeInfo) => {
      if (id === tabId && info.status === "complete") finish();
    };
    chrome.tabs.onUpdated.addListener(onUpdated);
    chrome.tabs.get(tabId).then((tab) => {
      if (tab.status === "complete") finish();
    }).catch(() => finish());
    setTimeout(finish, timeoutMs);
  });
}

/** Ensure a forum tab exists (background) for cookie-aware fetches via content script. */
export async function ensureForumTab(
  url = `${BASE_URL}/forums/du-doan-xsmb/`,
): Promise<number> {
  const existing = await findForumTabIds();
  if (existing.length > 0) return existing[0];

  const tab = await chrome.tabs.create({ url, active: false });
  if (!tab.id) throw new Error("Cannot open forum tab");
  await waitForTabComplete(tab.id);
  await sleep(500);
  return tab.id;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function sendTabMessage<T>(
  tabId: number,
  message: Record<string, unknown>,
): Promise<T | undefined> {
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      return (await chrome.tabs.sendMessage(tabId, message)) as T;
    } catch {
      try {
        await chrome.scripting.executeScript({
          target: { tabId },
          files: ["content.js"],
        });
        await sleep(200);
        return (await chrome.tabs.sendMessage(tabId, message)) as T;
      } catch {
        if (attempt < 2) await sleep(400);
      }
    }
  }
  return undefined;
}

/** In-page fetch via MAIN world — shares tab cookies (unlike service worker fetch). */
async function fetchHtmlViaExecuteScript(tabId: number, url: string): Promise<string | null> {
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      const results = await chrome.scripting.executeScript({
        target: { tabId },
        world: "MAIN",
        func: async (fetchUrl: string) => {
          try {
            const res = await fetch(fetchUrl, { credentials: "include" });
            if (!res.ok) return "";
            return await res.text();
          } catch {
            return "";
          }
        },
        args: [url],
      });
      const html = results?.[0]?.result;
      if (typeof html === "string" && html.length > 500) return html;
    } catch {
      /* retry */
    }
    if (attempt < 2) await sleep(400);
  }
  return null;
}

/** Fetch forum HTML in tab context — shares browser cookies (reliable vs service worker). */
export async function fetchForumHtmlInTab(url: string): Promise<string | null> {
  const tabId = await ensureForumTab();
  const viaScript = await fetchHtmlViaExecuteScript(tabId, url);
  if (viaScript) return viaScript;

  const result = await sendTabMessage<{ ok?: boolean; html?: string }>(tabId, {
    type: "FETCH_FORUM_HTML",
    url,
  });
  return result?.html || null;
}
