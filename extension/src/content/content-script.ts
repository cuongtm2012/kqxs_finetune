/** Login + UI sync chạy trong context trang forum (cookie dùng chung với tab). */

interface AuthPayload {
  username: string;
  password: string;
  remember: boolean;
  login_url: string;
}

function isPageLoggedIn(): boolean {
  const root = document.documentElement;
  return (
    root.className.includes("LoggedIn") ||
    !!document.querySelector("#accountAlerts, .accountPopup, .navTab.account.PopupControl")
  );
}

function extractCsrf(html: string): string | null {
  const fromInput = html.match(/name="_xfToken"\s+value="([^"]+)"/i)?.[1];
  if (fromInput) return fromInput;
  const fromJs = html.match(/_csrfToken:\s*"([^"]+)"/i)?.[1];
  if (fromJs) return fromJs;
  return html.match(/csrf=([A-Za-z0-9]+)/i)?.[1] || null;
}

function hideLoginOverlay(): void {
  document.querySelectorAll(
    "#LoginForm, .xenOverlay, .OverlayCloser, .errorOverlay",
  ).forEach((el) => {
    const host = el.closest(".xenOverlay") || el;
    if (host instanceof HTMLElement) host.style.display = "none";
  });
  document.querySelectorAll(".overlay").forEach((el) => {
    if (el instanceof HTMLElement) el.style.display = "none";
  });
  document.body.classList.remove("OverlayOpen");
  document.documentElement.classList.remove("LoggedOut");
  document.documentElement.classList.add("LoggedIn");
}

async function loginInTab(auth: AuthPayload): Promise<{ ok: boolean; error?: string }> {
  if (isPageLoggedIn()) {
    hideLoginOverlay();
    return { ok: true };
  }

  try {
    const loginUrl = auth.login_url || "https://forumketqua.net/login/";
    const loginPage = await fetch(loginUrl, { credentials: "include" });
    const loginHtml = await loginPage.text();
    const token = extractCsrf(loginHtml);
    if (!token) return { ok: false, error: "Missing CSRF token" };

    const body = new URLSearchParams({
      login: auth.username,
      password: auth.password,
      remember: auth.remember ? "1" : "0",
      _xfToken: token,
      redirect: location.pathname + location.search,
    });

    const res = await fetch("https://forumketqua.net/login/login", {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        Referer: loginUrl,
      },
      body: body.toString(),
      redirect: "follow",
    });
    const resultHtml = await res.text();

    if (resultHtml.includes("LoggedIn") || isPageLoggedIn()) {
      hideLoginOverlay();
      setTimeout(() => location.reload(), 50);
      return { ok: true };
    }

    setTimeout(() => location.reload(), 50);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "LOGIN_IN_TAB") {
    loginInTab(message.auth as AuthPayload).then(sendResponse);
    return true;
  }
  if (message?.type === "SYNC_LOGIN_UI") {
    if (isPageLoggedIn()) hideLoginOverlay();
    else location.reload();
    sendResponse({ ok: true });
    return true;
  }
  if (message?.type === "PARSE_PAGE") {
    const posts: unknown[] = [];
    document.querySelectorAll('li.message[id^="post-"]').forEach((el) => {
      const postId = el.id.replace("post-", "");
      const user =
        el.getAttribute("data-author") ||
        el.querySelector<HTMLElement>(".username")?.textContent?.trim() ||
        "";
      const timeEl = el.querySelector("time.DateTime");
      const raw = Number(timeEl?.getAttribute("data-time") || "0");
      const postedAtMs = raw > 0 && raw < 1e11 ? raw * 1000 : raw || Date.now();
      const content = el.querySelector(".messageText")?.textContent?.trim() || "";
      if (user && content.length > 15) {
        posts.push({ post_id: postId, user, posted_at_ms: postedAtMs, raw_content: content });
      }
    });
    sendResponse({ posts });
    return true;
  }
  return undefined;
});

// Ẩn overlay login nếu trang đã LoggedIn (sau reload)
if (isPageLoggedIn()) hideLoginOverlay();
