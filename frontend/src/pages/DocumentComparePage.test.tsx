import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import { getNodeDiff } from "../api/client";
import type {
  CompareResponse,
  DocumentVersionsResponse,
  EffectivityView,
  SummarizeResponse,
} from "../types";
import { DocumentComparePage } from "./DocumentComparePage";

const BASE_EFFECTIVITY: EffectivityView = {
  status: "active",
  verification: "verified",
  level: "document",
  as_of_date: "2026-01-15",
  notes: [],
  verification_source: "source_provenance",
  verified_by: null,
  verified_at: "2026-01-01T00:00:00Z",
  pending_proposals: 0,
  clause_level_reviewed: false,
  data_date: null,
};

function makeVersions(
  docId: string,
  docNumber: string,
  title: string,
  related: DocumentVersionsResponse["related_amendment_documents"] = [],
): DocumentVersionsResponse {
  return {
    document: {
      id: docId,
      title,
      document_number: docNumber,
      doc_type: "circular",
      issuing_body: "Bộ Công an",
    },
    versions: [
      {
        id: `${docId}-v2`,
        version_number: 2,
        publication_date: "2025-02-01",
        effective_from: "2025-03-01",
        is_current: true,
        based_on_version_id: `${docId}-v1`,
        reviewed_at: "2025-02-10T10:00:00Z",
      },
      {
        id: `${docId}-v1`,
        version_number: 1,
        publication_date: "2021-01-01",
        effective_from: "2021-02-01",
        is_current: false,
        based_on_version_id: null,
        reviewed_at: "2021-01-15T10:00:00Z",
      },
    ],
    related_amendment_documents: related,
  };
}

function makeCompareResponse(overrides: Partial<CompareResponse> = {}): CompareResponse {
  return {
    comparison_id: "cmp-1",
    mode: "versions",
    as_of_date: "2026-01-15",
    left_doc: {
      id: "doc-1",
      title: "Thông tư mẫu A",
      document_number: "10/2021/TT-BCA",
      doc_type: "circular",
      issuing_body: "Bộ Công an",
      version_id: "doc-1-v1",
      version_number: 1,
      effectivity: BASE_EFFECTIVITY,
    },
    right_doc: {
      id: "doc-1",
      title: "Thông tư mẫu A",
      document_number: "10/2021/TT-BCA",
      doc_type: "circular",
      issuing_body: "Bộ Công an",
      version_id: "doc-1-v2",
      version_number: 2,
      effectivity: BASE_EFFECTIVITY,
    },
    summary: {
      total_items: 2,
      added: 0,
      removed: 0,
      modified: 1,
      moved_or_renumbered: 0,
      unchanged: 1,
      high_impact_changes: 1,
      explicit_amendment_links: 0,
      deterministic_highlights: ["Khoản 2 Điều 18: sửa đổi nội dung — thời hạn: 10 ngày, 15 ngày"],
    },
    items: [
      {
        item_key: "item_0000",
        change_kind: "unchanged",
        content_also_modified: false,
        alignment_method: "structural_key",
        alignment_score: 1,
        impact_level: "low",
        signals: {
          deadlines_changed: [],
          amounts_changed: [],
          dates_changed: [],
          modality_shifted: false,
          exception_changed: false,
          impact_level: "low",
        },
        amendment_link: null,
        left: {
          node_id: "node-1-left",
          member_node_ids: ["node-1-left"],
          citation_label: "Điều 1",
          structural_key: "dieu:1",
          text_original: "Phạm vi điều chỉnh giữ nguyên.",
          page_start: 1,
          page_end: 1,
        },
        right: {
          node_id: "node-1-right",
          member_node_ids: ["node-1-right"],
          citation_label: "Điều 1",
          structural_key: "dieu:1",
          text_original: "Phạm vi điều chỉnh giữ nguyên.",
          page_start: 1,
          page_end: 1,
        },
        diff_segments: [{ op: "equal", text: "Phạm vi điều chỉnh giữ nguyên." }],
      },
      {
        item_key: "item_0001",
        change_kind: "modified",
        content_also_modified: false,
        alignment_method: "structural_key",
        alignment_score: 0.75,
        impact_level: "high",
        signals: {
          deadlines_changed: [
            { value_num: 10, unit_normalized: "ngay", raw_text: "10 ngày" },
            { value_num: 15, unit_normalized: "ngay", raw_text: "15 ngày" },
          ],
          amounts_changed: [],
          dates_changed: [],
          modality_shifted: true,
          exception_changed: false,
          impact_level: "high",
        },
        amendment_link: null,
        left: {
          node_id: "node-2-left",
          member_node_ids: ["node-2-left"],
          citation_label: "Khoản 2 Điều 18",
          structural_key: "dieu:18/khoan:2",
          text_original: "Tổ chức được phép nộp hồ sơ trong 10 ngày.",
          page_start: 8,
          page_end: 8,
        },
        right: {
          node_id: "node-2-right",
          member_node_ids: ["node-2-right"],
          citation_label: "Khoản 2 Điều 18",
          structural_key: "dieu:18/khoan:2",
          text_original: "Tổ chức phải nộp hồ sơ trong 15 ngày.",
          page_start: 9,
          page_end: 9,
        },
        diff_segments: [
          { op: "equal", text: "Tổ chức " },
          { op: "delete", text: "được phép" },
          { op: "insert", text: "phải" },
          { op: "equal", text: " nộp hồ sơ trong " },
          { op: "delete", text: "10 ngày" },
          { op: "insert", text: "15 ngày" },
          { op: "equal", text: "." },
        ],
      },
    ],
    disclaimer: "Gợi ý tự động — cần chuyên viên thẩm định trước khi áp dụng",
    ...overrides,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("DocumentComparePage", () => {
  it("supports versions mode, filters, display switch, and Markdown clipboard copy", async () => {
    const compareBodies: Array<Record<string, unknown>> = [];
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });

    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (input: string, init?: RequestInit) => {
        if (input.endsWith("/api/v1/search/comprehensive")) {
          return new Response(
            JSON.stringify({
              documents: [
                {
                  document_id: "doc-1",
                  title: "Thông tư mẫu A",
                  display_title: "Thông tư mẫu A",
                  document_number: "10/2021/TT-BCA",
                  doc_type: "circular",
                  issuing_body: "Bộ Công an",
                  source_format: "pdf",
                },
              ],
            }),
            { status: 200 },
          );
        }
        if (input.endsWith("/api/v1/documents/doc-1/versions")) {
          return new Response(
            JSON.stringify(makeVersions("doc-1", "10/2021/TT-BCA", "Thông tư mẫu A")),
            { status: 200 },
          );
        }
        if (input.endsWith("/api/v1/compare/documents")) {
          compareBodies.push(JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>);
          return new Response(JSON.stringify(makeCompareResponse()), { status: 200 });
        }
        return new Response("{}", { status: 200 });
      }),
    );

    render(<DocumentComparePage accessToken="tok-1" />);

    const pickerInput = screen.getByLabelText("Văn bản cần so sánh phiên bản");
    fireEvent.change(pickerInput, { target: { value: "10/2021" } });
    fireEvent.click(screen.getByRole("button", { name: "Tìm văn bản" }));

    const pickBtn = await screen.findByRole("button", { name: /10\/2021\/TT-BCA/ });
    fireEvent.click(pickBtn);

    await screen.findByLabelText("Phiên bản cũ (vế A)");
    const compareBtn = screen.getByRole("button", { name: "So sánh" });
    await waitFor(() => expect(compareBtn).toBeEnabled());
    fireEvent.click(compareBtn);

    const region = await screen.findByRole("region", { name: "Kết quả so sánh" });
    expect(compareBodies).toEqual([
      {
        mode: "versions",
        left_document_id: "doc-1",
        right_document_id: "doc-1",
        left_version_id: "doc-1-v1",
        right_version_id: "doc-1-v2",
        as_of_date: null,
        only_changes: false,
        include_embeddings: true,
      },
    ]);

    const cards = within(region).getByRole("group", { name: "Tổng hợp kết quả so sánh" });
    expect(cards).toHaveTextContent("1Sửa đổi");
    expect(cards).toHaveTextContent("1Không đổi");

    // Default filter hides unchanged Điều 1; shows Khoản 2 Điều 18 with signals
    expect(within(region).queryByText("Phạm vi điều chỉnh giữ nguyên.")).not.toBeInTheDocument();
    expect(within(region).getByText("Thời hạn: 10 ngày → 15 ngày")).toBeInTheDocument();
    expect(within(region).getByText("Tính bắt buộc thay đổi")).toBeInTheDocument();
    expect(
      within(region).getByRole("button", { name: "Mở gốc vế A (trang 8)" }),
    ).toBeInTheDocument();
    expect(
      within(region).getByRole("button", { name: "Mở gốc vế B (trang 9)" }),
    ).toBeInTheDocument();

    // Uncheck "Chỉ xem điểm thay đổi" -> Điều 1 appears
    const onlyChangesCheckbox = within(region).getByLabelText("Chỉ xem điểm thay đổi");
    expect(onlyChangesCheckbox).toBeChecked();
    fireEvent.click(onlyChangesCheckbox);
    expect(within(region).getAllByText("Phạm vi điều chỉnh giữ nguyên.").length).toBe(2);

    // Impact filter "high" hides low-impact unchanged item
    fireEvent.change(within(region).getByLabelText("Mức tác động"), {
      target: { value: "high" },
    });
    expect(within(region).queryByText("Phạm vi điều chỉnh giữ nguyên.")).not.toBeInTheDocument();
    expect(
      within(region).getAllByText("Khoản 2 Điều 18", { selector: "strong" }).length,
    ).toBe(2);

    // Switch side-by-side -> inline -> side-by-side
    const inlineBtn = within(region).getByRole("button", { name: "Gộp dòng (Inline)" });
    const sideBtn = within(region).getByRole("button", { name: "Song song (2 cột)" });
    fireEvent.click(inlineBtn);
    expect(inlineBtn).toHaveAttribute("aria-pressed", "true");
    expect(region.querySelector(".compare-items")).toHaveAttribute("data-display", "inline");
    fireEvent.click(sideBtn);
    expect(sideBtn).toHaveAttribute("aria-pressed", "true");
    expect(region.querySelector(".compare-items")).toHaveAttribute("data-display", "side_by_side");

    // Copy Markdown report
    fireEvent.click(
      within(region).getByRole("button", { name: "Sao chép báo cáo đối chiếu (Markdown)" }),
    );
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const copied = writeText.mock.calls[0][0] as string;
    expect(copied).toContain("10/2021/TT-BCA");
    expect(copied).toContain("Khoản 2 Điều 18");
    expect(copied).toContain("trang 8");
    expect(copied).toContain("Gợi ý tự động — cần chuyên viên thẩm định trước khi áp dụng");
    expect(await within(region).findByText("Đã sao chép báo cáo Markdown")).toBeInTheDocument();
  });

  it("supports amendment_pair suggestion click (including swap) and cross_document mode", async () => {
    const compareBodies: Array<Record<string, unknown>> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (input: string, init?: RequestInit) => {
        if (input.endsWith("/api/v1/search/comprehensive")) {
          const body = JSON.parse(String(init?.body ?? "{}")) as { q?: string };
          const isB = body.q === "docB";
          return new Response(
            JSON.stringify({
              documents: [
                {
                  document_id: isB ? "doc-b" : "doc-a",
                  title: isB ? "Văn bản B" : "Văn bản A",
                  display_title: isB ? "Văn bản B" : "Văn bản A",
                  document_number: isB ? "20/2025/TT" : "10/2021/TT",
                  doc_type: "circular",
                },
              ],
            }),
            { status: 200 },
          );
        }
        if (input.endsWith("/api/v1/documents/doc-a/versions")) {
          return new Response(
            JSON.stringify(
              makeVersions("doc-a", "10/2021/TT", "Văn bản A", [
                {
                  id: "doc-b",
                  title: "Văn bản B",
                  document_number: "20/2025/TT",
                  doc_type: "circular",
                  issuing_body: null,
                  directions: ["amended_by_this_document"],
                  actions: ["modify"],
                },
              ]),
            ),
            { status: 200 },
          );
        }
        if (input.endsWith("/api/v1/documents/doc-b/versions")) {
          return new Response(
            JSON.stringify(makeVersions("doc-b", "20/2025/TT", "Văn bản B")),
            { status: 200 },
          );
        }
        if (input.endsWith("/api/v1/compare/documents")) {
          const payload = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
          compareBodies.push(payload);
          return new Response(
            JSON.stringify(
              makeCompareResponse({
                mode: payload.mode as CompareResponse["mode"],
                summary: {
                  ...makeCompareResponse().summary,
                  explicit_amendment_links: payload.mode === "amendment_pair" ? 1 : 0,
                },
              }),
            ),
            { status: 200 },
          );
        }
        return new Response("{}", { status: 200 });
      }),
    );

    render(<DocumentComparePage accessToken="tok-1" />);

    fireEvent.click(screen.getByLabelText("So sánh gốc – sửa đổi/bổ sung"));
    fireEvent.change(screen.getByLabelText("Văn bản gốc (vế A)"), { target: { value: "docA" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Tìm văn bản" })[0]);
    fireEvent.click(await screen.findByRole("button", { name: /10\/2021\/TT/ }));

    // Suggestion shows swap explanation and swaps sides so original stays on side A
    const suggestionBtn = await screen.findByRole("button", { name: "20/2025/TT — sửa đổi" });
    expect(
      screen.getByText(/hai vế sẽ đổi chỗ/),
    ).toBeInTheDocument();
    fireEvent.click(suggestionBtn);

    const leftLine = document.querySelector('.compare-picked[data-side="left"]');
    const rightLine = document.querySelector('.compare-picked[data-side="right"]');
    expect(leftLine).toHaveTextContent("20/2025/TT");
    expect(rightLine).toHaveTextContent("10/2021/TT");

    fireEvent.click(screen.getByRole("button", { name: "So sánh" }));
    await screen.findByRole("region", { name: "Kết quả so sánh" });
    expect(compareBodies[0]).toMatchObject({
      mode: "amendment_pair",
      left_document_id: "doc-b",
      right_document_id: "doc-a",
      left_version_id: null,
      right_version_id: null,
    });

    // Switch to cross_document and pick both sides explicitly
    fireEvent.click(screen.getByLabelText("So sánh 2 văn bản cùng chủ đề"));
    fireEvent.change(screen.getByLabelText("Văn bản vế A"), { target: { value: "docA" } });
    fireEvent.change(screen.getByLabelText("Văn bản vế B"), { target: { value: "docB" } });
    const searchButtons = screen.getAllByRole("button", { name: "Tìm văn bản" });
    fireEvent.click(searchButtons[0]);
    fireEvent.click(searchButtons[1]);
    fireEvent.click(await screen.findByRole("button", { name: /10\/2021\/TT/ }));
    fireEvent.click(await screen.findByRole("button", { name: /20\/2025\/TT/ }));

    fireEvent.click(screen.getByRole("button", { name: "So sánh" }));
    await screen.findByRole("region", { name: "Kết quả so sánh" });
    expect(compareBodies[1]).toMatchObject({
      mode: "cross_document",
      left_document_id: "doc-a",
      right_document_id: "doc-b",
    });
  });

  it("escapes XSS payloads in diff segments, labels, and amendment quotes as plain text", async () => {
    const xss = "<img src=x onerror=alert(1)>";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (input: string) => {
        if (input.endsWith("/api/v1/documents/doc-1/versions")) {
          return new Response(
            JSON.stringify(makeVersions("doc-1", "10/2021/TT-BCA", "Thông tư mẫu A")),
            { status: 200 },
          );
        }
        if (input.endsWith("/api/v1/compare/documents")) {
          const base = makeCompareResponse();
          base.items[1] = {
            ...base.items[1],
            alignment_method: "explicit_amendment",
            amendment_link: {
              action: "modify",
              valid_from: "2025-06-01",
              source_quote: xss,
            },
            left: {
              ...base.items[1].left!,
              citation_label: `Điều 1 ${xss}`,
              text_original: `Cũ ${xss}`,
            },
            diff_segments: [
              { op: "delete", text: xss },
              { op: "insert", text: "Mới an toàn" },
            ],
          };
          return new Response(JSON.stringify(base), { status: 200 });
        }
        return new Response("{}", { status: 200 });
      }),
    );

    const { container } = render(
      <DocumentComparePage
        accessToken="tok-1"
        preset={{ mode: "versions", leftDocumentId: "doc-1" }}
      />,
    );
    const compareBtn = await screen.findByRole("button", { name: "So sánh" });
    await waitFor(() => expect(compareBtn).toBeEnabled());
    fireEvent.click(compareBtn);

    const region = await screen.findByRole("region", { name: "Kết quả so sánh" });
    expect(container.querySelector("img")).toBeNull();
    expect(region.textContent).toContain(xss);
  });

  it("renders AI summary verified/needs_review badges and deterministic fallback reason", async () => {
    let summarizeMode: "ai" | "fallback" = "ai";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (input: string) => {
        if (input.endsWith("/api/v1/documents/doc-1/versions")) {
          return new Response(
            JSON.stringify(makeVersions("doc-1", "10/2021/TT-BCA", "Thông tư mẫu A")),
            { status: 200 },
          );
        }
        if (input.endsWith("/api/v1/compare/documents")) {
          return new Response(JSON.stringify(makeCompareResponse()), { status: 200 });
        }
        if (input.endsWith("/api/v1/compare/summarize")) {
          const aiReply: SummarizeResponse =
            summarizeMode === "ai"
              ? {
                  comparison_id: "sum-fresh-uuid",
                  mode_used: "ai",
                  reason: null,
                  executive_summary: "Thời hạn tăng từ 10 ngày lên 15 ngày.",
                  summary_status: "needs_review",
                  key_changes: [
                    {
                      point: "Thời hạn tăng từ 10 ngày lên 15 ngày.",
                      item_keys: ["item_0001"],
                      evidence_ids: ["ev_node-2-left"],
                      status: "verified",
                      check_notes: [],
                    },
                    {
                      point: "Phạt 999 triệu đồng.",
                      item_keys: ["item_0001"],
                      evidence_ids: ["ev_node-2-right"],
                      status: "needs_review",
                      check_notes: ["NUMBER_NOT_IN_EVIDENCE"],
                    },
                  ],
                  deterministic_highlights: ["Khoản 2 Điều 18: sửa đổi nội dung"],
                  external_api_used: false,
                  ai_limited: false,
                  disclaimer: "Gợi ý tự động — cần chuyên viên thẩm định trước khi áp dụng",
                }
              : {
                  comparison_id: "sum-fallback-uuid",
                  mode_used: "deterministic_fallback",
                  reason: "remote_blocked_by_document_policy",
                  executive_summary: null,
                  summary_status: null,
                  key_changes: [],
                  deterministic_highlights: ["Khoản 2 Điều 18: sửa đổi nội dung"],
                  external_api_used: false,
                  ai_limited: false,
                  disclaimer: "Gợi ý tự động — cần chuyên viên thẩm định trước khi áp dụng",
                };
          return new Response(JSON.stringify(aiReply), { status: 200 });
        }
        return new Response("{}", { status: 200 });
      }),
    );

    render(
      <DocumentComparePage
        accessToken="tok-1"
        preset={{ mode: "versions", leftDocumentId: "doc-1" }}
      />,
    );
    const compareBtn = await screen.findByRole("button", { name: "So sánh" });
    await waitFor(() => expect(compareBtn).toBeEnabled());
    fireEvent.click(compareBtn);
    await screen.findByRole("region", { name: "Kết quả so sánh" });

    const aiBtn = screen.getByRole("button", { name: "Tóm tắt bằng AI" });
    fireEvent.click(aiBtn);

    const aiSection = screen.getByRole("region", { name: "Tóm tắt thay đổi cốt lõi bằng AI" });
    expect(
      await within(aiSection).findByText("Tóm tắt tham khảo từ AI — đã đối chiếu số liệu với căn cứ"),
    ).toBeInTheDocument();
    expect(within(aiSection).getByText("Đã đối chiếu căn cứ")).toBeInTheDocument();
    expect(within(aiSection).getAllByText("Cần thẩm định").length).toBeGreaterThanOrEqual(2);
    expect(within(aiSection).getByText("(NUMBER_NOT_IN_EVIDENCE)")).toBeInTheDocument();
    expect(within(aiSection).getAllByRole("link", { name: "[item_0001]" })[0]).toHaveAttribute(
      "href",
      "#compare-item-item_0001",
    );

    // Fallback banner + reason
    summarizeMode = "fallback";
    fireEvent.click(screen.getByRole("button", { name: "Tóm tắt bằng AI" }));
    expect(
      await within(aiSection).findByText(
        "Tóm tắt xác định (không dùng AI) — Văn bản thuộc danh mục hạn chế xử lý từ xa; chỉ dùng kết quả xác định.",
      ),
    ).toBeInTheDocument();
    expect(within(aiSection).getByText("Khoản 2 Điều 18: sửa đổi nội dung")).toBeInTheDocument();
  });

  it("resets compare state and preset cleanly on logout in App", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (input: string) => {
        if (input.endsWith("/api/v1/system/mode")) {
          return new Response(JSON.stringify({ effective_mode: "LOCAL" }), { status: 200 });
        }
        if (input.endsWith("/api/v1/auth/login")) {
          return new Response(
            JSON.stringify({
              access_token: "tok-user",
              token_type: "bearer",
              expires_at: "2026-12-01T00:00:00Z",
              user: {
                id: "00000000-0000-0000-0000-000000000002",
                username: "reader",
                display_name: "Chuyên viên",
                roles: ["USER"],
                permissions: ["rag.query"],
                must_change_password: false,
              },
            }),
            { status: 200 },
          );
        }
        if (input.endsWith("/api/v1/auth/logout")) {
          return new Response(null, { status: 204 });
        }
        if (input.endsWith("/api/v1/search/comprehensive")) {
          return new Response(
            JSON.stringify({
              result_set_id: "rs-1",
              query: "99/2025",
              as_of_date: "2026-01-15",
              page: 1,
              page_size: 20,
              view: "documents",
              total_items: 1,
              total_documents: 1,
              has_more: false,
              items: [],
              hidden_items: 0,
              scope: {
                documents_in_scope: 1,
                categories: ["Chung"],
                as_of_date: "2026-01-15",
                statement: "1 văn bản trong phạm vi",
              },
              channels: {},
              totals: {
                clauses: 1,
                documents: 1,
                only_semantic: 0,
                only_relation: 0,
                only_concept: 0,
              },
              ranking: { reranked: false, reranked_count: 0, total: 1 },
              concepts: [],
              sections: [{ key: "relevant", label: "Phù hợp nhất", count: 1, collapsed: false }],
              display: "all",
              documents: [
                {
                  rank: 1,
                  document_id: "doc-preset",
                  document_version_id: "doc-preset-v2",
                  title: "Nghị định preset",
                  display_title: "Nghị định preset",
                  document_number: "99/2025/NĐ-CP",
                  doc_type: "decree",
                  source_format: "pdf",
                  effectivity: BASE_EFFECTIVITY,
                  best_tier: "exact",
                  tier_counts: { exact: 1 },
                  listing: false,
                  matched_clause_count: 1,
                  has_more_clauses: false,
                  clauses: [],
                  groups: [],
                },
              ],
            }),
            { status: 200 },
          );
        }
        if (input.endsWith("/api/v1/documents/doc-preset/versions")) {
          return new Response(
            JSON.stringify(makeVersions("doc-preset", "99/2025/NĐ-CP", "Nghị định preset")),
            { status: 200 },
          );
        }
        if (input.endsWith("/api/v1/compare/documents")) {
          return new Response(JSON.stringify(makeCompareResponse()), { status: 200 });
        }
        return new Response("{}", { status: 200 });
      }),
    );

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Đăng nhập" }));
    fireEvent.change(screen.getByLabelText("Tên đăng nhập"), { target: { value: "reader" } });
    fireEvent.change(screen.getByLabelText("Mật khẩu"), { target: { value: "UserPass!2026" } });
    fireEvent.click(screen.getByRole("button", { name: "Đăng nhập" }));
    await screen.findByText(/Chuyên viên/);

    // Go to Search -> click "So sánh" quick action on card -> compare preset loads
    fireEvent.click(screen.getByRole("button", { name: "Tìm kiếm văn bản" }));
    fireEvent.change(screen.getByLabelText("Nội dung cần tìm"), {
      target: { value: "99/2025" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Tìm kiếm" }));
    const quickCompareBtn = await screen.findByRole("button", { name: "So sánh" });
    fireEvent.click(quickCompareBtn);

    expect(await screen.findByRole("heading", { name: "So sánh văn bản" })).toBeInTheDocument();
    const compareBtn = await screen.findByRole("button", { name: "So sánh" });
    await waitFor(() => expect(compareBtn).toBeEnabled());
    fireEvent.click(compareBtn);
    await screen.findByRole("region", { name: "Kết quả so sánh" });

    // Logout returns to chat and clears comparePreset
    fireEvent.click(screen.getByRole("button", { name: "Đăng xuất" }));
    await waitFor(() => expect(screen.queryByRole("heading", { name: "So sánh văn bản" })).not.toBeInTheDocument());

    // Log back in and open Compare tab -> clean slate, no old preset or result
    fireEvent.click(screen.getByRole("button", { name: "Đăng nhập" }));
    fireEvent.change(screen.getByLabelText("Tên đăng nhập"), { target: { value: "reader" } });
    fireEvent.change(screen.getByLabelText("Mật khẩu"), { target: { value: "UserPass!2026" } });
    fireEvent.click(screen.getByRole("button", { name: "Đăng nhập" }));
    await screen.findByText(/Chuyên viên/);

    fireEvent.click(screen.getByRole("button", { name: "So sánh văn bản" }));
    expect(screen.queryByText(/99\/2025\/NĐ-CP/)).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Kết quả so sánh" })).not.toBeInTheDocument();
  });

  it("drops stale compare responses silently after a selection change (R5a)", async () => {
    const compareDeferred = deferred<Response>();
    let compareSignal: AbortSignal | undefined;

    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (input: string, init?: RequestInit) => {
        if (input.endsWith("/api/v1/documents/doc-1/versions")) {
          return new Response(
            JSON.stringify(makeVersions("doc-1", "10/2021/TT-BCA", "Thông tư mẫu A")),
            { status: 200 },
          );
        }
        if (input.endsWith("/api/v1/compare/documents")) {
          compareSignal = init?.signal ?? undefined;
          return compareDeferred.promise;
        }
        return new Response("{}", { status: 200 });
      }),
    );

    render(
      <DocumentComparePage
        accessToken="tok-1"
        preset={{ mode: "versions", leftDocumentId: "doc-1" }}
      />,
    );
    const compareBtn = await screen.findByRole("button", { name: "So sánh" });
    await waitFor(() => expect(compareBtn).toBeEnabled());
    fireEvent.click(compareBtn);
    expect(screen.getByText("Đang so sánh…", { selector: "p" })).toBeInTheDocument();

    // Change as-of date while compare is in flight -> aborts & clears busy
    fireEvent.change(screen.getByLabelText("Hiệu lực tại ngày"), {
      target: { value: "2026-06-01" },
    });
    expect(compareSignal?.aborted).toBe(true);
    expect(screen.queryByText("Đang so sánh…", { selector: "p" })).not.toBeInTheDocument();

    // Late resolution of old compare must be silently ignored (no result, no alert)
    compareDeferred.resolve(new Response(JSON.stringify(makeCompareResponse()), { status: 200 }));
    await waitFor(() => expect(compareSignal?.aborted).toBe(true));
    expect(screen.queryByRole("region", { name: "Kết quả so sánh" })).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("never renders a stale summarize response under a newer comparison_id (R5b)", async () => {
    let compareSeq = 0;
    const oldSummarizeDeferred = deferred<Response>();
    let summarizeCalls = 0;
    let oldSummarizeSignal: AbortSignal | undefined;

    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (input: string, init?: RequestInit) => {
        if (input.endsWith("/api/v1/documents/doc-1/versions")) {
          return new Response(
            JSON.stringify(makeVersions("doc-1", "10/2021/TT-BCA", "Thông tư mẫu A")),
            { status: 200 },
          );
        }
        if (input.endsWith("/api/v1/compare/documents")) {
          compareSeq += 1;
          return new Response(
            JSON.stringify(makeCompareResponse({ comparison_id: `cmp-${compareSeq}` })),
            { status: 200 },
          );
        }
        if (input.endsWith("/api/v1/compare/summarize")) {
          summarizeCalls += 1;
          if (summarizeCalls === 1) {
            oldSummarizeSignal = init?.signal ?? undefined;
            return oldSummarizeDeferred.promise;
          }
          const fresh: SummarizeResponse = {
            comparison_id: "sum-new",
            mode_used: "ai",
            reason: null,
            executive_summary: "Tóm tắt mới hợp lệ.",
            summary_status: "verified",
            key_changes: [],
            deterministic_highlights: [],
            external_api_used: false,
            ai_limited: false,
            disclaimer: "Gợi ý tự động — cần chuyên viên thẩm định trước khi áp dụng",
          };
          return new Response(JSON.stringify(fresh), { status: 200 });
        }
        return new Response("{}", { status: 200 });
      }),
    );

    render(
      <DocumentComparePage
        accessToken="tok-1"
        preset={{ mode: "versions", leftDocumentId: "doc-1" }}
      />,
    );
    const compareBtn = await screen.findByRole("button", { name: "So sánh" });
    await waitFor(() => expect(compareBtn).toBeEnabled());
    fireEvent.click(compareBtn);
    await screen.findByRole("region", { name: "Kết quả so sánh" });

    // Start summarize under cmp-1
    fireEvent.click(screen.getByRole("button", { name: "Tóm tắt bằng AI" }));
    expect(screen.getByText(/Đang tóm tắt… có thể mất tới một phút/)).toBeInTheDocument();

    // Change as-of date -> aborts summarize, clears cmp-1; run cmp-2
    fireEvent.change(screen.getByLabelText("Hiệu lực tại ngày"), {
      target: { value: "2026-07-01" },
    });
    expect(oldSummarizeSignal?.aborted).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "So sánh" }));
    await screen.findByRole("region", { name: "Kết quả so sánh" });

    // Old summarize resolves late -> must NOT render under cmp-2
    const staleReply: SummarizeResponse = {
      comparison_id: "sum-stale",
      mode_used: "ai",
      reason: null,
      executive_summary: "Tóm tắt cũ bị rò rỉ.",
      summary_status: "verified",
      key_changes: [],
      deterministic_highlights: [],
      external_api_used: false,
      ai_limited: false,
      disclaimer: "Gợi ý tự động — cần chuyên viên thẩm định trước khi áp dụng",
    };
    oldSummarizeDeferred.resolve(new Response(JSON.stringify(staleReply), { status: 200 }));
    await Promise.resolve();
    expect(screen.queryByText("Tóm tắt cũ bị rò rỉ.")).not.toBeInTheDocument();
    expect(document.querySelector(".compare-ai-result")).toBeNull();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    // Fresh summarize under cmp-2 succeeds
    fireEvent.click(screen.getByRole("button", { name: "Tóm tắt bằng AI" }));
    expect(await screen.findByText("Tóm tắt mới hợp lệ.")).toBeInTheDocument();
  });

  it("aborts in-flight requests cleanly on unmount with zero console errors (R5c)", async () => {
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const compareDeferred = deferred<Response>();
    let capturedSignal: AbortSignal | undefined;

    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (input: string, init?: RequestInit) => {
        if (input.endsWith("/api/v1/documents/doc-1/versions")) {
          return new Response(
            JSON.stringify(makeVersions("doc-1", "10/2021/TT-BCA", "Thông tư mẫu A")),
            { status: 200 },
          );
        }
        if (input.endsWith("/api/v1/compare/documents")) {
          capturedSignal = init?.signal ?? undefined;
          return compareDeferred.promise;
        }
        return new Response("{}", { status: 200 });
      }),
    );

    const { unmount } = render(
      <DocumentComparePage
        accessToken="tok-1"
        preset={{ mode: "versions", leftDocumentId: "doc-1" }}
      />,
    );
    const compareBtn = await screen.findByRole("button", { name: "So sánh" });
    await waitFor(() => expect(compareBtn).toBeEnabled());
    fireEvent.click(compareBtn);

    unmount();
    expect(capturedSignal?.aborted).toBe(true);
    compareDeferred.resolve(new Response(JSON.stringify(makeCompareResponse()), { status: 200 }));
    await Promise.resolve();
    expect(consoleErrorSpy).not.toHaveBeenCalled();
  });

  it("keeps the 65s timeout on getNodeDiff even when as_of_date query param is set", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((_input: string, init?: RequestInit) => {
        return new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("Aborted", "AbortError"));
          });
        });
      }),
    );

    const pending = getNodeDiff("tok-1", "node-123", { asOfDate: "2026-05-01" });
    const caughtPromise = pending.catch((err: unknown) => err);

    // At 25s (> default 20s timeout), the request must still be pending (not timed out).
    await vi.advanceTimersByTimeAsync(25000);
    let settled = false;
    void caughtPromise.then(() => {
      settled = true;
    });
    await Promise.resolve();
    expect(settled).toBe(false);

    // At 65s, it triggers CLIENT_TIMEOUT.
    await vi.advanceTimersByTimeAsync(41000);
    const err = await caughtPromise;
    expect(err).toMatchObject({ code: "CLIENT_TIMEOUT", status: 408 });
  });
});
