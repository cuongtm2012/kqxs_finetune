import { BASE_URL } from "../types/forum.js";
import {
  extractXfToken,
  isLoggedInHtml,
  isLoginPage,
  pageHasReadableForumContent,
} from "./forum-html-parser.js";
import { loginInForumTab, syncForumTabUi, fetchForumHtmlInTab } from "./forum-tabs.js";
import { getForumAuth, patchRuntimeStatus } from "./storage.js";

const UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

const HTML_CACHE_TTL_MS = 5 * 60 * 1000;
const htmlCache = new Map<string, { html: string; at: number }>();

export function clearForumHtmlCache(): void {
  htmlCache.clear();
}

export async function forumFetch(url: string, init: RequestInit = {}): Promise<Response> {
  return fetch(url, {
    ...init,
    credentials: "include",
    headers: {
      "User-Agent": UA,
      Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
      ...(init.headers || {}),
    },
  });
}

export async function fetchForumHtml(
  url: string,
  retryLogin = true,
  options: { bypassCache?: boolean } = {},
): Promise<string> {
  const cached = htmlCache.get(url);
  if (!options.bypassCache && cached && Date.now() - cached.at < HTML_CACHE_TTL_MS) {
    return cached.html;
  }

  try {
    const tabHtml = await fetchForumHtmlInTab(url);
    if (tabHtml && pageHasReadableForumContent(tabHtml)) {
      htmlCache.set(url, { html: tabHtml, at: Date.now() });
      return tabHtml;
    }
  } catch {
    /* fall through to service worker fetch */
  }

  let res = await forumFetch(url);
  let html = await res.text();
  const needsLogin =
    !isLoggedInHtml(html) &&
    !pageHasReadableForumContent(html) &&
    ((res.redirected && res.url.includes("/login")) || isLoginPage(html));
  if (needsLogin) {
    if (!retryLogin) throw new Error("NOT_LOGGED_IN");
    const ok = await ensureLoggedIn();
    if (!ok) throw new Error("LOGIN_FAILED");
    res = await forumFetch(url);
    html = await res.text();
    if (
      !isLoggedInHtml(html) &&
      !pageHasReadableForumContent(html) &&
      isLoginPage(html)
    ) {
      throw new Error("LOGIN_FAILED");
    }
  }
  htmlCache.set(url, { html, at: Date.now() });
  return html;
}

export async function hasValidSession(): Promise<boolean> {
  try {
    const res = await forumFetch(`${BASE_URL}/forums/du-doan-xsmb/`);
    const html = await res.text();
    return isLoggedInHtml(html);
  } catch {
    return false;
  }
}

export async function ensureLoggedIn(): Promise<boolean> {
  await patchRuntimeStatus({ auth_status: "checking" });
  if (await hasValidSession()) {
    await syncForumTabUi();
    await patchRuntimeStatus({ auth_status: "logged_in", last_error: undefined });
    return true;
  }

  const auth = await getForumAuth();

  // Ưu tiên login trong tab forum → cookie + UI đồng bộ với trang user đang xem
  const tabOk = await loginInForumTab(auth);
  if (tabOk && (await hasValidSession())) {
    await patchRuntimeStatus({
      auth_status: "logged_in",
      last_login_at: new Date().toISOString(),
      last_error: undefined,
    });
    return true;
  }

  try {
    const loginPage = await forumFetch(auth.login_url || `${BASE_URL}/login/`);
    const loginHtml = await loginPage.text();
    const token = extractXfToken(loginHtml);
    if (!token) throw new Error("Missing _xfToken");

    const body = new URLSearchParams({
      login: auth.username,
      password: auth.password,
      remember: auth.remember ? "1" : "0",
      cookie_check: "1",
      _xfToken: token,
      redirect: "",
    });

    const postRes = await forumFetch(`${BASE_URL}/login/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        Referer: auth.login_url || `${BASE_URL}/login/`,
      },
      body: body.toString(),
      redirect: "follow",
    });
    const loginResult = await postRes.text();
    const ok = isLoggedInHtml(loginResult) || (await hasValidSession());
    if (ok) await syncForumTabUi();
    await patchRuntimeStatus({
      auth_status: ok ? "logged_in" : "error",
      last_login_at: ok ? new Date().toISOString() : undefined,
      last_error: ok ? undefined : "Đăng nhập forum thất bại — kiểm tra user/pass",
    });
    return ok;
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    await patchRuntimeStatus({ auth_status: "error", last_error: msg });
    return false;
  }
}
