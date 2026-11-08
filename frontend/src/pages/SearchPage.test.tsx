import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { SearchPage } from "./SearchPage";

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

const NODE = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";

function clause(tier: string, match: string, text: string) {
  return {
    rank: 1, node_id: NODE, document_id: "d1", document_number: "10/2014/TT-BCA",
    title: "Thông Tư Quy định việc xử lý tố cáo", label: "Khoản 2 Điều 18",
    heading: "Điều 18. Báo cáo công tác giải quyết tố cáo", node_type: "clause", path: "x",
    page: 8, quote_exact: text, snippet: text, viewer_url: `/api/v1/citations/ev_${NODE}/pdf`,
    original_url: `/api/v1/citations/ev_${NODE}/original?as_of_date=2026-11-08`,
    excerpt: { start: 0, end: text.length, text, truncated_before: false,
               truncated_after: false, highlights: [{ start: 3, end: 18 }] },
    channels: ["exact", "semantic"], section: "unverified", tier, match, matched_terms: [],
    listing: false, groups: [],
  };
}

function page(extra: Record<string, unknown> = {}) {
  const text = "2. Báo cáo định kỳ hàng tháng về tố cáo.";
  return {
    result_set_id: "rs_1", query: "báo cáo định kỳ", as_of_date: "2026-11-08", page: 1,
    page_size: 10, view: "documents", total_items: 3, total_documents: 1, has_more: false,
    items: [], hidden_items: 0,
    documents: [{
      rank: 1, document_id: "d1", document_version_id: "v1", document_number: "10/2014/TT-BCA",
      title: "Thông Tư Quy định việc xử lý tố cáo", display_title: "Quy định việc xử lý tố cáo",
      kind_label: null, doc_type: "circular", issuing_body: "Bộ Công an",
      publication_date: "2014-03-04", source_format: "pdf",
      original_url: `/api/v1/citations/ev_${NODE}/original?as_of_date=2026-11-08`,
      effectivity: null, best_tier: "direct", tier_counts: { direct: 1 }, listing: false,
      matched_clause_count: 3, has_more_clauses: true, groups: [],
      clauses: [clause("direct", "phrase", text)],
    }],
    scope: { documents_in_scope: 100, categories: [], data_date: null, as_of_date: "2026-11-08",
             statement: "Kết quả là những gì tìm thấy trong phạm vi trên." },
    channels: { exact: { count: 2, enabled: true }, semantic: { count: 1, enabled: true } },
    totals: { clauses: 3, documents: 2, only_semantic: 1, only_relation: 0, only_concept: 0 },
    ranking: { reranked: false, reranked_count: 0, total: 3 },
    concepts: [], sections: [{ key: "unverified", label: "Chưa xác minh", count: 3, collapsed: false }],
    display: "default", understood: { phrases: ["báo cáo định kỳ"], mode: "keywords" },
    tiers: { direct: 1, related: 0, weak: 2, unscored: 0 },
    ...extra,
  };
}

function install() {
  const fetcher = vi.fn().mockImplementation((url: string) => {
    if (url.endsWith("/api/v1/categories")) return Promise.resolve(new Response("[]", { status: 200 }));
    if (url.endsWith("/api/v1/search/comprehensive")) {
      return Promise.resolve(new Response(JSON.stringify(page()), { status: 200 }));
    }
    if (url.includes("/documents/d1")) {
      return Promise.resolve(new Response(JSON.stringify({
        result_set_id: "rs_1", document_id: "d1",
        clauses: [clause("direct", "phrase", "A"), { ...clause("related", "semantic", "B"), node_id: "n2" }],
      }), { status: 200 }));
    }
    if (url.includes("/api/v1/search/comprehensive/rs_1")) {
      return Promise.resolve(new Response(JSON.stringify(page({
        documents: [{ ...page().documents[0], document_id: "d2", document_number: "06/VBHN-BCA",
                      best_tier: "weak", clauses: [clause("weak", "partial", "Báo cáo số liệu.")] }],
      })), { status: 200 }));
    }
    return Promise.resolve(new Response("{}", { status: 200 }));
  });
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

function bodyOf(fetcher: ReturnType<typeof install>, suffix: string) {
  const call = fetcher.mock.calls.find(([url]) => String(url).endsWith(suffix));
  return JSON.parse(String((call?.[1] as RequestInit).body));
}

async function searchFor(text: string) {
  fireEvent.change(screen.getByRole("searchbox", { name: "Nội dung cần tìm" }), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: "Tìm kiếm" }));
  await screen.findByRole("region", { name: "Kết quả tìm kiếm" });
}

it("asks for one fixed comprehensive result set grouped by document", async () => {
  const fetcher = install();
  render(<SearchPage accessToken="token" />);
  await searchFor("báo cáo định kỳ");
  const body = bodyOf(fetcher, "/api/v1/search/comprehensive");
  expect(body).toMatchObject({ q: "báo cáo định kỳ", view: "documents", mode: "auto",
                               tier: ["direct", "related", "unscored"] });
  expect(body.channels).toBeUndefined();
  const card = screen.getByRole("article", { name: "10/2014/TT-BCA" });
  expect(within(card).getByText("Quy định việc xử lý tố cáo")).toBeInTheDocument();
  expect(within(card).getByText("04/03/2014")).toBeInTheDocument();
  expect(within(card).getByText("Khớp đúng cụm từ")).toBeInTheDocument();
  expect(within(card).getByText("báo cáo định kỳ".replace("b", "B"), { selector: "mark" }))
    .toBeInTheDocument();
  expect(within(card).getByText("PDF gốc, mở tab mới tại trang 8")).toBeInTheDocument();
  expect(screen.getByText(/«báo cáo định kỳ»/)).toBeInTheDocument();
});

it("sends exact-phrase and all-words searches to the exact channel only", async () => {
  const fetcher = install();
  render(<SearchPage accessToken="token" />);
  fireEvent.click(screen.getByLabelText("Tìm chính xác cụm từ"));
  await searchFor("báo cáo định kỳ");
  expect(bodyOf(fetcher, "/api/v1/search/comprehensive")).toMatchObject({
    mode: "phrase", channels: ["exact"],
  });
  expect(window.location.search).toContain("mode=phrase");
});

it("keeps partial matches in a separate, collapsed list and loads more clauses", async () => {
  const fetcher = install();
  render(<SearchPage accessToken="token" />);
  await searchFor("báo cáo định kỳ");
  fireEvent.click(screen.getByRole("button", { name: /Xem thêm 2 điều khoản khớp/ }));
  await waitFor(() => expect(fetcher.mock.calls.some(([url]) => String(url).includes("/documents/d1"))).toBe(true));
  const weakButton = screen.getByRole("button", { name: /2 điều khoản chỉ khớp một phần/ });
  expect(weakButton).toHaveAttribute("aria-expanded", "false");
  fireEvent.click(weakButton);
  await screen.findByRole("article", { name: "06/VBHN-BCA" });
  const weakCall = fetcher.mock.calls.find(([url]) => String(url).includes("/rs_1?"));
  expect(String(weakCall?.[0])).toContain("tier=weak");
});

it("opens an old shared link (?q=…) with its query and runs it", async () => {
  window.history.replaceState(null, "", "/?q=b%C3%A1o+c%C3%A1o&mode=keywords");
  const fetcher = install();
  render(<SearchPage accessToken="token" />);
  await screen.findByRole("region", { name: "Kết quả tìm kiếm" });
  expect(bodyOf(fetcher, "/api/v1/search/comprehensive")).toMatchObject({
    q: "báo cáo", mode: "keywords", channels: ["exact"],
  });
});

it("asks to log in before searching", () => {
  render(<SearchPage />);
  expect(screen.getByText("Đăng nhập để tìm kiếm trong văn bản đã duyệt.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Tìm kiếm" })).toBeDisabled();
});
