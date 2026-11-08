import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import { join, normalize, extname } from "node:path";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("../dist", import.meta.url));
const PORT = 8731;
const CDP_PORT = 9333;
const CHROME = process.env.CHROME_PATH;
if (!CHROME) {
  throw new Error("CHROME_PATH is required for the browser E2E harness.");
}
const ORIGIN = `http://127.0.0.1:${PORT}`;
const MIME = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".map": "application/json", ".svg": "image/svg+xml" };

// ---- HƯ CẤU (fictional) fixtures: only for exercising the UI in a real browser ----
const PHRASE = "báo cáo định kỳ và thường xuyên";
const QUOTE = "Các bộ, ngành thực hiện báo cáo định kỳ và thường xuyên theo quy định của pháp luật.";
const SNIPPET = "thực hiện báo cáo định kỳ và thường xuyên theo quy định";
const SNIPPET_START = QUOTE.indexOf(SNIPPET);
const HIGHLIGHT_START = QUOTE.indexOf(PHRASE);
const DOC1 = {
  document_id: "doc-e2e-1", document_version_id: "ver-e2e-1",
  document_number: "385/2026/NĐ-CP", title: "Quy định chế độ báo cáo định kỳ (HƯ CẤU)",
  doc_type: "decree", issuing_body: "Chính phủ",
  official_url: "https://vanban.chinhphu.vn/385-2026", matched_clause_count: 3,
  clause_page: 1, clause_page_size: 5, has_more_clauses: true,
  clauses: [
    { node_id: "11111111-1111-1111-1111-111111111111", label: "Khoản 1 Điều 5", page: 12,
      match_type: "exact_phrase", amendment_state: "active", amendment_as_of: "2026-10-31",
      quote_exact: QUOTE, snippet: SNIPPET, snippet_start: SNIPPET_START,
      highlights: [{ start: HIGHLIGHT_START, end: HIGHLIGHT_START + PHRASE.length }],
      viewer_url: "/api/v1/citations/ev_11111111-1111-1111-1111-111111111111/pdf?as_of_date=2026-10-31",
      source_hash: "a".repeat(64) },
    { node_id: "22222222-2222-2222-2222-222222222222", label: "Khoản 3 Điều 9", page: 20,
      match_type: "exact_phrase", amendment_state: "modified", amendment_as_of: "2026-07-01",
      quote_exact: "Báo cáo định kỳ và thường xuyên gửi trước ngày 20 tháng 12 hằng năm.",
      snippet: "Báo cáo định kỳ và thường xuyên gửi trước ngày 20 tháng 12", snippet_start: 0,
      highlights: [{ start: 0, end: PHRASE.length }],
      viewer_url: "/api/v1/citations/ev_22222222-2222-2222-2222-222222222222/pdf?as_of_date=2026-07-01",
      source_hash: "b".repeat(64) },
  ],
};
const DOC2 = {
  document_id: "doc-e2e-2", document_version_id: "ver-e2e-2", document_number: null,
  title: "Hướng dẫn gửi báo cáo (HƯ CẤU)", doc_type: "circular", issuing_body: "Bộ Tài chính",
  official_url: null, matched_clause_count: 1, clause_page: 1, clause_page_size: 5,
  has_more_clauses: false,
  clauses: [{ node_id: "33333333-3333-3333-3333-333333333333", label: "Khoản 2 Điều 3", page: null,
    match_type: "phrase_folded", amendment_state: "unknown", amendment_as_of: "2026-10-31",
    quote_exact: "Bao cao dinh ky va thuong xuyen nop ve bo.", snippet: "Bao cao dinh ky",
    snippet_start: 0, highlights: [{ start: 40, end: 60 }], viewer_url: null,
    source_hash: "c".repeat(64) }],
};
const PAGE1 = {
  query: { original: "báo cáo định kỳ", phrase: PHRASE, mode: "phrase", normalization_revision: "norm-r1" },
  phrase_found: true, totals: { documents: 2, clauses: 4, approximate_matches_hidden: 7 },
  page: 1, page_size: 20, has_more: false, effectivity_snapshot_status: "stale",
  results: [DOC1, DOC2], approximate: { collapsed: true, total_clauses: 7 }, empty_reason: null,
};
const PAGE2 = {
  ...PAGE1,
  results: [{ ...DOC1, clause_page: 2, has_more_clauses: false, matched_clause_count: 3, clauses: [
    { ...DOC1.clauses[0], node_id: "66666666-6666-6666-6666-666666666666", label: "Khoản 5 Điều 12",
      page: 31, quote_exact: "Báo cáo định kỳ và thường xuyên nộp bổ sung khi có yêu cầu.",
      snippet: "Báo cáo định kỳ và thường xuyên nộp bổ sung", snippet_start: 0,
      highlights: [{ start: 0, end: PHRASE.length }],
      viewer_url: "/api/v1/citations/ev_66666666-6666-6666-6666-666666666666/pdf?as_of_date=2026-10-31" },
  ] }],
};
const APPROX = {
  ...PAGE1, phrase_found: false,
  totals: { documents: 1, clauses: 1, approximate_matches_hidden: 0 },
  results: [{ ...DOC2, document_id: "doc-approx-e2e", document_number: "12/2026/TT-BTC",
    title: "Hướng dẫn tổng hợp báo cáo (HƯ CẤU)", matched_clause_count: 1, has_more_clauses: false,
    clauses: [{ ...DOC2.clauses[0], node_id: "44444444-4444-4444-4444-444444444444",
      label: "Khoản 1 Điều 2", page: 3, match_type: "any_term",
      quote_exact: "Báo cáo tổng hợp được gửi trước ngày 31 tháng 12.",
      snippet: "Báo cáo tổng hợp", snippet_start: 0, highlights: [{ start: 0, end: 16 }],
      viewer_url: null }] }],
  approximate: { collapsed: true, total_clauses: 1 },
};
const USER = { id: "00000000-0000-0000-0000-000000000010", username: "nguoidung",
  display_name: "Người dùng thử", roles: ["USER"], permissions: ["rag.query"], must_change_password: false };

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const apiRequests = [];
const result = { steps: [], failures: [] };

function json(res, body, status = 200) {
  res.writeHead(status, { "Content-Type": "application/json", "Cache-Control": "no-store" });
  res.end(JSON.stringify(body));
}

const server = createServer(async (req, res) => {
  const pathname = decodeURIComponent((req.url || "/").split("?")[0]);
  if (pathname.startsWith("/api/")) {
    apiRequests.push(req.url);
    if (pathname === "/api/v1/system/mode") return json(res, { effective_mode: "LOCAL" });
    if (pathname === "/api/v1/auth/login") return json(res, {
      access_token: "fixture-token", token_type: "bearer", expires_at: "2030-01-01T00:00:00Z", user: USER });
    if (pathname === "/api/v1/categories") return json(res, [
      { id: "cat-1", code: "C1", name: "Danh mục A (HƯ CẤU)", remote_processing_allowed: false }]);
    if (pathname === "/api/v1/search/approximate") return json(res, APPROX);
    if (pathname === "/api/v1/search") {
      const clausePage = new URL(req.url, ORIGIN).searchParams.get("clause_page");
      return json(res, clausePage === "2" ? PAGE2 : PAGE1);
    }
    if (pathname.startsWith("/api/v1/citations/")) {
      res.writeHead(200, { "Content-Type": "application/pdf", "Cache-Control": "no-store" });
      return res.end(Buffer.from("%PDF-1.4\n% fixture\n"));
    }
    return json(res, { code: "NOT_FOUND", message: "not found" }, 404);
  }
  const safe = normalize(pathname).replace(/^(\.\.[/\\])+/, "").replace(/^[\\/]+/, "");
  const filePath = join(ROOT, safe || "index.html");
  try {
    const data = await readFile(filePath);
    res.writeHead(200, { "Content-Type": MIME[extname(filePath)] ?? "application/octet-stream" });
    res.end(data);
  } catch {
    res.writeHead(404, { "Content-Type": "text/plain" });
    res.end("not found");
  }
});
await new Promise((r) => server.listen(PORT, "127.0.0.1", r));

const profile = mkdtempSync(join(tmpdir(), "rea-chrome-"));
const chrome = spawn(CHROME, [
  "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
  "--disable-extensions", "--mute-audio",
  `--remote-debugging-port=${CDP_PORT}`, `--user-data-dir=${profile}`,
  "--window-size=1280,800", `${ORIGIN}/`,
], { stdio: "ignore" });

async function findPage() {
  for (let i = 0; i < 80; i += 1) {
    try {
      const targets = await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json();
      const page = targets.find((t) => t.type === "page" && String(t.url).startsWith(ORIGIN));
      if (page?.webSocketDebuggerUrl) return page;
    } catch { /* not ready */ }
    await sleep(250);
  }
  throw new Error("CDP endpoint did not expose a page target");
}

const target = await findPage();
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = () => reject(new Error("websocket failed")); });
let nextId = 0;
const pending = new Map();
const networkUrls = [];
socket.onmessage = (event) => {
  const message = JSON.parse(event.data);
  if (message.id && pending.has(message.id)) { pending.get(message.id)(message); pending.delete(message.id); return; }
  if (message.method === "Network.requestWillBeSent") networkUrls.push(message.params.request.url);
};
const send = (method, params = {}) => new Promise((resolve) => {
  const id = ++nextId; pending.set(id, resolve); socket.send(JSON.stringify({ id, method, params }));
});
await send("Runtime.enable"); await send("Page.enable"); await send("Network.enable");

async function evaluate(expression) {
  const reply = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
  if (reply.result?.exceptionDetails) throw new Error(`evaluate failed: ${expression} :: ${reply.result.exceptionDetails.text}`);
  return reply.result?.result?.value;
}
async function waitFor(expression, label, timeout = 10000) {
  const started = Date.now();
  while (Date.now() - started < timeout) { if (await evaluate(expression)) return true; await sleep(120); }
  result.failures.push(`timeout waiting for ${label}`);
  return false;
}
const text = (selector) => evaluate(`(document.querySelector(${JSON.stringify(selector)})?.textContent ?? "").trim()`);
const attr = (selector, name) => evaluate(`document.querySelector(${JSON.stringify(selector)})?.getAttribute(${JSON.stringify(name)}) ?? null`);
function check(condition, message) { if (!condition) result.failures.push(message); }
async function setInput(selector, value) {
  await evaluate(`(() => { const el = document.querySelector(${JSON.stringify(selector)}); const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set; setter.call(el, ${JSON.stringify(value)}); el.dispatchEvent(new Event("input", { bubbles: true })); })()`);
  await sleep(120);
}
async function clickButtonByText(label) {
  return evaluate(`(() => { const b = Array.from(document.querySelectorAll("button")).find((el) => el.textContent.trim() === ${JSON.stringify(label)}); if (!b) return false; b.click(); return true; })()`);
}

try {
  await waitFor("Boolean(document.querySelector('.app-shell'))", "app shell");
  result.steps.push("app shell mounted");
  const navLabels = await evaluate("Array.from(document.querySelectorAll('.topbar-controls button')).map((b) => b.textContent.trim())");
  result.steps.push(`nav: ${JSON.stringify(navLabels)}`);
  check(navLabels.includes("Hỏi đáp") && navLabels.includes("Tìm kiếm văn bản"), "missing user portal nav");

  // 1. Log in through the real login dialog (fixture API, no real backend).
  check(await clickButtonByText("Đăng nhập"), "login button not found");
  await waitFor("Boolean(document.querySelector('.login-dialog'))", "login dialog");
  await setInput('.login-dialog input[aria-label="Tên đăng nhập"]', "nguoidung");
  await setInput('.login-dialog input[aria-label="Mật khẩu"]', "FixturePassword!2026");
  check(await evaluate("!document.querySelector('.login-dialog button[type=submit]').disabled"), "login submit still disabled");
  await evaluate("document.querySelector('.login-dialog button[type=submit]').click()");
  await waitFor("Boolean(document.querySelector('.user-pill'))", "authenticated user pill", 8000);
  result.steps.push(`session: ${await text(".user-pill")}`);

  // 2. Open the search page from the top navigation.
  check(await clickButtonByText("Tìm kiếm văn bản"), "search nav not clickable");
  await waitFor("Boolean(document.querySelector('.search-page h1'))", "search page");
  result.steps.push(`heading: ${await text(".search-page h1")}`);
  result.steps.push(`searchbox label: ${await text(".search-query-field")}`);
  result.steps.push(`placeholder: ${await attr("input[type=search]", "placeholder")}`);
  result.steps.push(`result aria-live: ${await attr('[role=region][aria-label="Kết quả tìm kiếm"]', "aria-live")}`);
  result.steps.push(`filters toggle aria-expanded: ${await attr(".search-filter-toggle", "aria-expanded")}`);

  // 3. Search with the exact-phrase option.
  await setInput("input[type=search]", "báo cáo định kỳ");
  await evaluate("document.querySelector('.search-phrase-row input').click()");
  await waitFor("!document.querySelector('.search-submit').disabled", "submit enabled");
  await evaluate("document.querySelector('.search-submit').click()");
  await waitFor("Boolean(document.querySelector('.search-doc-group'))", "first results");

  result.steps.push(`summary: ${await text(".search-summary")}`);
  result.steps.push(`stale warning: ${await text(".search-stale")}`);
  result.steps.push(`count label: ${await text(".search-doc-group .status-pill")}`);
  result.steps.push(`document heading: ${await text(".search-doc-group h3")}`);
  result.steps.push(`match badge: ${await text('.match-tag[data-match="exact_phrase"]')}`);
  result.steps.push(`effectivity badge: ${await text('.effectivity-tag[data-state="modified"]')}`);
  result.steps.push(`mark text: ${await text(".search-clause-snippet mark")}`);
  result.steps.push(`official link: ${await attr(".search-doc-meta a", "href")} target=${await attr(".search-doc-meta a", "target")} rel=${await attr(".search-doc-meta a", "rel")}`);
  result.steps.push(`group aria-expanded: ${await attr(".search-doc-toggle", "aria-expanded")}`);

  const phraseRequest = apiRequests.find((url) => url.startsWith("/api/v1/search?"));
  result.steps.push(`search request: ${phraseRequest}`);
  check(Boolean(phraseRequest && phraseRequest.includes("mode=phrase")), "search request missing mode=phrase");
  check(Boolean(phraseRequest && phraseRequest.includes("clause_page_size=5")), "search request missing clause_page_size=5");
  check((await text(".search-stale")).includes("Dữ liệu hiệu lực đang được cập nhật"), "stale warning text mismatch");
  check((await text(".search-doc-group .status-pill")) === "Hiển thị 2/3 khoản", "clause count label mismatch");

  // 4. Load the next per-document clause window.
  const moreClicked = await evaluate("(() => { const b = Array.from(document.querySelectorAll('button')).find((el) => el.textContent.trim() === 'Xem thêm khoản khớp'); if (!b) return false; b.click(); return true; })()");
  check(moreClicked, "load-more button not found");
  await waitFor("document.querySelector('.search-doc-group .status-pill')?.textContent.trim() === 'Hiển thị 3/3 khoản'", "clause window 2");
  result.steps.push(`clause page 2 label: ${await text(".search-doc-group .status-pill")}`);
  result.steps.push(`clause labels now: ${JSON.stringify(await evaluate("Array.from(document.querySelectorAll('.search-doc-group .search-clause-label')).map((el) => el.textContent.trim())"))}`);
  const clausePageRequest = apiRequests.find((url) => /(?:\?|&)clause_page=2(?:&|$)/.test(url));
  result.steps.push(`clause_page=2 request: ${clausePageRequest}`);
  check(Boolean(clausePageRequest), "no clause_page=2 request observed");

  // 5. Open the collapsed approximate section.
  await evaluate("Array.from(document.querySelectorAll('button')).find((b) => b.textContent.includes('Kết quả gần đúng')).click()");
  await waitFor("Boolean(document.querySelector('.match-tag[data-match=any_term]'))", "approximate results");
  result.steps.push(`approximate request: ${apiRequests.find((url) => url.startsWith("/api/v1/search/approximate"))}`);
  result.steps.push(`approximate badge: ${await text('.match-tag[data-match="any_term"]')}`);

  // 6. Open the cited PDF through viewer_url.
  await evaluate("Array.from(document.querySelectorAll('button')).find((b) => b.textContent.trim() === 'Mở trang PDF nguồn').click()");
  await waitFor("Boolean(document.querySelector('iframe.pdf-frame'))", "pdf iframe");
  result.steps.push(`pdf iframe: ${await attr("iframe.pdf-frame", "title")} src=${(await attr("iframe.pdf-frame", "src"))?.slice(0, 40)}…`);

  // 7. Local Mode: no request may leave the local origin.
  const external = networkUrls.filter((url) => /^https?:\/\//i.test(url) && !url.startsWith(`${ORIGIN}/`));
  const browserInternal = networkUrls.filter((url) => !/^https?:\/\//i.test(url));
  result.steps.push(`network requests observed: ${networkUrls.length}`);
  result.steps.push(`external http(s) origins: ${JSON.stringify(external)}`);
  result.steps.push(`browser-internal schemes (not network): ${JSON.stringify(browserInternal)}`);
  check(external.length === 0, `external requests observed: ${JSON.stringify(external)}`);
  const foreignApi = apiRequests.filter((url) => !url.startsWith("/api/v1/"));
  check(foreignApi.length === 0, `non-API requests: ${JSON.stringify(foreignApi)}`);
} catch (error) {
  result.failures.push(`exception: ${error.message}`);
} finally {
  try { socket.close(); } catch { /* ignore */ }
  chrome.kill();
  server.close();
  await sleep(300);
  console.log(JSON.stringify(result, null, 2));
  process.exit(result.failures.length > 0 ? 1 : 0);
}

