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
  try {
    await chrome.tabs.sendMessage(tabId, { type: "LOGIN_IN_TAB", auth });
    return true;
  } catch {
    // Content script chưa inject — inject rồi thử lại
    try {
      await chrome.scripting.executeScript({
        target: { tabId },
        files: ["content.js"],
      });
      await chrome.tabs.sendMessage(tabId, { type: "LOGIN_IN_TAB", auth });
      return true;
    } catch {
      return false;
    }
  }
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
