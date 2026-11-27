import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import type {
  AdminConflictFindingsResponse,
  AuthorityRuleListResponse,
  AuthorityRuleView,
  ConflictFindingView,
  ConflictScanDetailResponse,
  DocumentVersionsResponse,
} from "../types";
import { AdminPortal } from "./AdminPortal";
import { ConflictReviewPage } from "./ConflictReviewPage";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const TEST_FINDING_UNDETERMINED: ConflictFindingView = {
  id: "finding-1",
  run_id: "run-1",
  document_a_id: "doc-a",
  document_b_id: "doc-b",
  node_a_id: "node-a",
  node_b_id: "node-b",
  document_a_number: "10/2024/NĐ-CP",
  document_a_title: "Nghị định về xử phạt hành chính",
  document_b_number: "20/2024/TT-BTC",
  document_b_title: "Thông tư hướng dẫn hồ sơ",
  node_a_label: "Điều 5",
  node_a_path: "000005",
  node_a_text: "Thời hạn giải quyết hồ sơ là 10 ngày làm việc.",
  node_a_page_start: 3,
  node_b_label: "Điều 7",
  node_b_path: "000007",
  node_b_text: "Thời hạn giải quyết hồ sơ là 20 ngày làm việc.",
  node_b_page_start: 4,
  finding_type: "contradiction",
  severity: "high",
  detection_method: "rule",
  similarity_score: 0.89,
  shared_labels: ["thoi_han"],
  signals_json: { deadline_conflict: true },
  precedence_result: "undetermined_requires_review",
  precedence_basis_json: {
    status_a: "active",
    status_b: "unknown",
    as_of_date: "2026-01-15",
    tier_a: {
      rule_code: "decree_gov",
      doc_type: "decree",
      authority_rank: 30,
      authority_tier_label: "Nghị định (Chính phủ)",
    },
    tier_b: {
      rule_code: "circular_btc",
      doc_type: "circular",
      authority_rank: 40,
      authority_tier_label: "Thông tư (Bộ Tài chính)",
    },
    basis: "Cần đối chiếu phạm vi chuyên ngành giữa hai văn bản.",
    caveats: [
      "Kiểm tra nguyên tắc văn bản chuyên ngành (lex specialis): nếu văn bản ban hành trước là quy định chuyên ngành cụ thể, văn bản sau không tự động thay thế nếu không có điều khoản bãi bỏ/sửa đổi.",
    ],
  },
  explanation: "Khác biệt thời hạn giải quyết hồ sơ: 10 ngày làm việc so với 20 ngày làm việc.",
  ai_confidence: null,
  ai_verified: null,
  review_status: "pending",
  reviewed_by: null,
  reviewed_at: null,
  review_note: null,
  linked_amendment_id: null,
  created_at: "2026-01-15T08:00:00Z",
  reference_notice: "Gợi ý tự động — cần chuyên viên thẩm định trước khi áp dụng",
};

const TEST_FINDING_EXCEPTION: ConflictFindingView = {
  ...TEST_FINDING_UNDETERMINED,
  id: "finding-2",
  node_a_id: "node-a-2",
  node_b_id: "node-b-2",
  node_a_label: "Điều 8",
  node_b_label: "Điều 9",
  node_a_text: "Tổ chức phải nộp báo cáo định kỳ hàng quý.",
  node_b_text: "Trừ trường hợp doanh nghiệp siêu nhỏ được miễn báo cáo quý.",
  finding_type: "exception_refinement",
  severity: "medium",
  precedence_result: "higher_authority_a",
  precedence_basis_json: {
    status_a: "active",
    status_b: "active",
    as_of_date: "2026-01-15",
    basis: "Nghị định (Chính phủ, bậc 30) cao hơn Thông tư (Bộ Tài chính, bậc 40).",
    caveats: [],
  },
  explanation: "Vế B bổ sung ngoại lệ 'trừ trường hợp'.",
};

function makeScanDetail(
  overrides: Partial<ConflictScanDetailResponse> = {},
): ConflictScanDetailResponse {
  return {
    id: "run-1",
    run_id: "run-1",
    requested_by: "user-1",
    request_id: "req-12345678",
    status: "completed",
    scope_json: { document_ids: ["doc-a", "doc-b"], resolved_document_ids: ["doc-a", "doc-b"] },
    scope_document_count: 2,
    as_of_date: "2026-01-15",
    use_ai: false,
    model_profile_id: null,
    limits_json: { max_documents: 20 },
    progress_total: 4,
    progress_done: 4,
    summary_json: {
      total_documents: 2,
      total_normative_nodes: 8,
      candidate_pairs_evaluated: 4,
      total_findings: 2,
      by_severity: { high: 1, medium: 1, low: 0 },
      by_type: {
        contradiction: 1,
        overlap: 0,
        exception_refinement: 1,
        superseded_already: 0,
      },
      ai_used: false,
      ai_pairs_screened: 0,
      ai_verified: 0,
      ai_filtered: 0,
      ai_fallbacks: 0,
      dropped_documents_by_acl: 0,
      disclaimer: "Gợi ý tự động — cần chuyên viên thẩm định trước khi áp dụng.",
    },
    error_code: null,
    error_message: null,
    created_at: "2026-01-15T08:00:00Z",
    started_at: "2026-01-15T08:00:01Z",
    completed_at: "2026-01-15T08:00:03Z",
    expires_at: "2026-01-22T08:00:00Z",
    reference_notice: "Gợi ý tự động — cần chuyên viên thẩm định trước khi áp dụng",
    deduplicated: false,
    findings: [TEST_FINDING_UNDETERMINED, TEST_FINDING_EXCEPTION],
    total_findings: 2,
    hidden_due_to_acl: 0,
    disclaimer: "Gợi ý tự động — cần chuyên viên thẩm định trước khi áp dụng.",
    ...overrides,
  };
}

function makeVersionsDoc(docId: string, docNumber: string, title: string): DocumentVersionsResponse {
  return {
    document: {
      id: docId,
      title,
      document_number: docNumber,
      doc_type: "decree",
      issuing_body: "Chính phủ",
    },
    versions: [
      {
        id: `${docId}-v1`,
        version_number: 1,
        publication_date: "2024-01-10",
        effective_from: "2024-02-01",
        is_current: true,
        based_on_version_id: null,
        reviewed_at: "2024-01-15T00:00:00Z",
      },
    ],
    related_amendment_documents: [],
  };
}

describe("ConflictReviewPage & Phase 2 UI", () => {
  it("creates a scan from 2 picked docs, polls every 2s until completed, and renders caveats + ACL notice + filters", async () => {
    let pollCount = 0;
    const postedPayloads: Array<Record<string, unknown>> = [];

    const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.endsWith("/api/v1/categories")) {
        return Promise.resolve(
          new Response(
            JSON.stringify([
              { id: "cat-1", code: "THUE", name: "Thuế", remote_processing_allowed: false },
            ]),
            { status: 200 },
          ),
        );
      }
      if (url.includes("/api/v1/conflicts/scans?") && (!init?.method || init.method === "GET")) {
        return Promise.resolve(new Response(JSON.stringify({ total: 0, items: [] }), { status: 200 }));
      }
      if (url.endsWith("/api/v1/search/comprehensive")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              result_set_id: "rs-1",
              query: "2024",
              as_of_date: "2026-01-15",
              page: 1,
              page_size: 8,
              view: "documents",
              total_items: 2,
              has_more: false,
              items: [],
              documents: [
                {
                  rank: 1,
                  document_id: "doc-a",
                  document_version_id: "doc-a-v1",
                  document_number: "10/2024/NĐ-CP",
                  title: "Nghị định A",
                  doc_type: "decree",
                  best_tier: "direct",
                  tier_counts: {},
                  listing: false,
                  matched_clause_count: 1,
                  has_more_clauses: false,
                  clauses: [],
                  groups: [],
                },
                {
                  rank: 2,
                  document_id: "doc-b",
                  document_version_id: "doc-b-v1",
                  document_number: "20/2024/TT-BTC",
                  title: "Thông tư B",
                  doc_type: "circular",
                  best_tier: "direct",
                  tier_counts: {},
                  listing: false,
                  matched_clause_count: 1,
                  has_more_clauses: false,
                  clauses: [],
                  groups: [],
                },
              ],
              hidden_items: 0,
              scope: { documents_in_scope: 2, categories: [], as_of_date: "2026-01-15", statement: "" },
              channels: {},
              totals: { clauses: 0, documents: 2, only_semantic: 0, only_relation: 0, only_concept: 0 },
              ranking: { reranked: false, reranked_count: 0, total: 2 },
              concepts: [],
              sections: [],
              display: "all",
            }),
            { status: 200 },
          ),
        );
      }
      if (url.endsWith("/api/v1/conflicts/scans") && init?.method === "POST") {
        postedPayloads.push(JSON.parse(String(init.body)) as Record<string, unknown>);
        return Promise.resolve(
          new Response(
            JSON.stringify({
              run_id: "run-1",
              status: "queued",
              scope_document_count: 2,
              created_at: "2026-01-15T08:00:00Z",
              deduplicated: false,
            }),
            { status: 202 },
          ),
        );
      }
      if (url.endsWith("/api/v1/conflicts/scans/run-1")) {
        pollCount += 1;
        if (pollCount === 1) {
          return Promise.resolve(
            new Response(
              JSON.stringify(
                makeScanDetail({
                  status: "running",
                  progress_done: 1,
                  progress_total: 4,
                  findings: [],
                  total_findings: 0,
                  summary_json: null,
                }),
              ),
              { status: 200 },
            ),
          );
        }
        return Promise.resolve(
          new Response(
            JSON.stringify(makeScanDetail({ status: "completed", hidden_due_to_acl: 1 })),
            { status: 200 },
          ),
        );
      }
      return Promise.resolve(new Response("{}", { status: 200 }));
    });
    vi.stubGlobal("fetch", fetcher);

    render(<ConflictReviewPage accessToken="tok-user" />);

    await waitFor(() =>
      expect(fetcher.mock.calls.some(([u]) => String(u).endsWith("/api/v1/categories"))).toBe(true),
    );

    fireEvent.change(screen.getByLabelText("Tìm văn bản để thêm vào phạm vi"), {
      target: { value: "2024" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Tìm văn bản" }));

    const pickA = await screen.findByRole("button", { name: /10\/2024\/NĐ-CP/ });
    const pickB = screen.getByRole("button", { name: /20\/2024\/TT-BTC/ });
    fireEvent.click(pickA);
    fireEvent.click(pickB);

    // Enable fake timers only before starting the scan + polling loop.
    vi.useFakeTimers();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Bắt đầu rà soát mâu thuẫn" }));
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(postedPayloads).toHaveLength(1);
    expect(String(postedPayloads[0].request_id).length).toBeGreaterThanOrEqual(8);
    expect(postedPayloads[0].document_ids).toEqual(["doc-a", "doc-b"]);
    expect(postedPayloads[0].use_ai).toBe(false);
    expect(pollCount).toBe(1);
    expect(screen.getByText(/Đang xử lý lượt quét/)).toBeInTheDocument();

    // Advance 2000ms -> triggers second poll which returns completed.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    expect(pollCount).toBe(2);
    expect(screen.getByText(/Có 1 phát hiện đã bị ẩn/)).toBeInTheDocument();
    expect(
      screen.getByText(/Chưa xác định tự động — cần chuyên viên thẩm định/),
    ).toBeInTheDocument();
    expect(screen.getByText(/lex specialis/)).toBeInTheDocument();
    expect(screen.getAllByText(/Gợi ý tự động — cần chuyên viên thẩm định/).length).toBeGreaterThan(
      0,
    );

    // Further timer advancement must NOT poll again once completed.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    expect(pollCount).toBe(2);

    // Filter findings by type
    const filterGroup = screen.getByRole("group", { name: "Lọc theo loại phát hiện" });
    fireEvent.click(within(filterGroup).getByRole("button", { name: "Ngoại lệ / chi tiết hóa" }));
    expect(
      screen.queryByText(/Khác biệt thời hạn giải quyết hồ sơ/),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/Vế B bổ sung ngoại lệ/)).toBeInTheDocument();
  });

  it("cancels an active scan and stops polling", async () => {
    let pollCount = 0;
    const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.endsWith("/api/v1/categories")) {
        return Promise.resolve(
          new Response(
            JSON.stringify([
              { id: "cat-1", code: "THUE", name: "Thuế", remote_processing_allowed: false },
            ]),
            { status: 200 },
          ),
        );
      }
      if (url.includes("/api/v1/conflicts/scans?") && (!init?.method || init.method === "GET")) {
        return Promise.resolve(new Response(JSON.stringify({ total: 0, items: [] }), { status: 200 }));
      }
      if (url.endsWith("/api/v1/conflicts/scans") && init?.method === "POST") {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              run_id: "run-cancel",
              status: "queued",
              scope_document_count: 3,
              created_at: "2026-01-15T08:00:00Z",
              deduplicated: false,
            }),
            { status: 202 },
          ),
        );
      }
      if (url.endsWith("/api/v1/conflicts/scans/run-cancel") && (!init?.method || init.method === "GET")) {
        pollCount += 1;
        return Promise.resolve(
          new Response(
            JSON.stringify(
              makeScanDetail({
                id: "run-cancel",
                run_id: "run-cancel",
                status: "running",
                findings: [],
                total_findings: 0,
                summary_json: null,
              }),
            ),
            { status: 200 },
          ),
        );
      }
      if (url.endsWith("/api/v1/conflicts/scans/run-cancel/cancel") && init?.method === "POST") {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              ...makeScanDetail({
                id: "run-cancel",
                run_id: "run-cancel",
                status: "cancelled",
                error_code: "CONFLICT_SCAN_CANCELLED",
                findings: [],
                total_findings: 0,
                summary_json: null,
              }),
            }),
            { status: 200 },
          ),
        );
      }
      return Promise.resolve(new Response("{}", { status: 200 }));
    });
    vi.stubGlobal("fetch", fetcher);

    render(<ConflictReviewPage accessToken="tok-user" />);

    fireEvent.click(screen.getByLabelText("Quét theo 1 danh mục"));
    await waitFor(() => expect(screen.getByRole("option", { name: /Thuế/ })).toBeInTheDocument());

    vi.useFakeTimers();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Bắt đầu rà soát mâu thuẫn" }));
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(pollCount).toBe(1);
    const cancelBtn = screen.getByRole("button", { name: "Hủy lượt quét" });

    await act(async () => {
      fireEvent.click(cancelBtn);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.getByRole("status")).toHaveTextContent("Đã hủy");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    expect(pollCount).toBe(1);
  });

  it("jumps from ConflictFindingCard to DocumentComparePage in cross_document mode and resets on logout", async () => {
    const fetcher = vi.fn().mockImplementation((url: string) => {
      if (url.endsWith("/api/v1/system/mode")) {
        return Promise.resolve(new Response(JSON.stringify({ effective_mode: "LOCAL" }), { status: 200 }));
      }
      if (url.endsWith("/api/v1/auth/login")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              access_token: "tok-app",
              token_type: "bearer",
              expires_at: "2026-12-01T00:00:00Z",
              user: {
                id: "u1",
                username: "chuyenvien",
                display_name: "Chuyên viên",
                roles: ["USER"],
                permissions: ["rag.query"],
                must_change_password: false,
              },
            }),
            { status: 200 },
          ),
        );
      }
      if (url.endsWith("/api/v1/auth/logout")) {
        return Promise.resolve(new Response(null, { status: 204 }));
      }
      if (url.endsWith("/api/v1/categories")) {
        return Promise.resolve(new Response(JSON.stringify([]), { status: 200 }));
      }
      if (url.includes("/api/v1/conflicts/scans?")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({ total: 1, items: [makeScanDetail()] }),
            { status: 200 },
          ),
        );
      }
      if (url.endsWith("/api/v1/conflicts/scans/run-1")) {
        return Promise.resolve(new Response(JSON.stringify(makeScanDetail()), { status: 200 }));
      }
      if (url.endsWith("/api/v1/documents/doc-a/versions")) {
        return Promise.resolve(
          new Response(JSON.stringify(makeVersionsDoc("doc-a", "10/2024/NĐ-CP", "Nghị định A")), {
            status: 200,
          }),
        );
      }
      if (url.endsWith("/api/v1/documents/doc-b/versions")) {
        return Promise.resolve(
          new Response(JSON.stringify(makeVersionsDoc("doc-b", "20/2024/TT-BTC", "Thông tư B")), {
            status: 200,
          }),
        );
      }
      return Promise.resolve(new Response("{}", { status: 200 }));
    });
    vi.stubGlobal("fetch", fetcher);

    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "Đăng nhập" }));
    fireEvent.change(screen.getByLabelText("Tên đăng nhập"), { target: { value: "chuyenvien" } });
    fireEvent.change(screen.getByLabelText("Mật khẩu"), { target: { value: "Password!2026" } });
    fireEvent.click(screen.getByRole("button", { name: "Đăng nhập" }));

    const conflictsTab = await screen.findByRole("button", { name: "Rà soát mâu thuẫn" });
    fireEvent.click(conflictsTab);

    const viewBtn = await screen.findByRole("button", { name: "Xem kết quả" });
    fireEvent.click(viewBtn);

    const compareJumpButtons = await screen.findAllByRole("button", {
      name: "So sánh chi tiết 2 văn bản này",
    });
    fireEvent.click(compareJumpButtons[0]);

    // DocumentComparePage opens in cross_document mode with both sides prefilled
    await waitFor(() => {
      const crossRadio = screen.getByLabelText("So sánh 2 văn bản cùng chủ đề") as HTMLInputElement;
      expect(crossRadio.checked).toBe(true);
    });
    expect(await screen.findByText(/10\/2024\/NĐ-CP/)).toBeInTheDocument();
    expect(await screen.findByText(/20\/2024\/TT-BTC/)).toBeInTheDocument();

    // Logout resets view back to chat and unmounts compare/conflicts state
    fireEvent.click(screen.getByRole("button", { name: "Đăng xuất" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Hỏi đáp" })).toHaveAttribute("aria-current", "page"),
    );
  });

  it("triages findings and creates draft amendments in AdminPortal ConflictTriagePanel", async () => {
    const reviewPayloads: Array<Record<string, unknown>> = [];
    const triagePayload: AdminConflictFindingsResponse = {
      total: 1,
      items: [TEST_FINDING_UNDETERMINED],
      disclaimer: "Gợi ý tự động — cần chuyên viên thẩm định trước khi áp dụng.",
      reference_notice: "Gợi ý tự động — cần chuyên viên thẩm định trước khi áp dụng",
    };

    const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/api/v1/admin/conflicts/findings/finding-1/review") && init?.method === "POST") {
        reviewPayloads.push(JSON.parse(String(init.body)) as Record<string, unknown>);
        return Promise.resolve(
          new Response(
            JSON.stringify({
              finding_id: "finding-1",
              review_status: "linked_amendment",
              reviewed_by: "rev-1",
              reviewed_at: "2026-01-16T09:00:00Z",
              review_note: "Xác nhận xung đột thời hạn",
              linked_amendment_id: "amend-draft-1",
              amendment_review_status: "draft",
              reference_notice: "Gợi ý tự động — cần chuyên viên thẩm định trước khi áp dụng",
            }),
            { status: 200 },
          ),
        );
      }
      if (url.includes("/api/v1/admin/conflicts/findings")) {
        return Promise.resolve(new Response(JSON.stringify(triagePayload), { status: 200 }));
      }
      return Promise.resolve(new Response("[]", { status: 200 }));
    });
    vi.stubGlobal("fetch", fetcher);

    render(
      <AdminPortal
        accessToken="rev-token"
        currentUser={{
          id: "rev-1",
          username: "reviewer",
          display_name: "Người thẩm định",
          roles: ["REVIEWER"],
          permissions: [],
          must_change_password: false,
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Rà soát mâu thuẫn" }));

    expect(await screen.findByText(/Hàng đợi thẩm định phát hiện mâu thuẫn/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Ghi chú thẩm định"), {
      target: { value: "Xác nhận xung đột thời hạn" },
    });
    fireEvent.click(screen.getByLabelText("Tạo đề xuất sửa đổi (bản nháp)"));
    expect(screen.getByText(/lưu ở trạng thái bản nháp \(draft\)/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Xác nhận" }));

    await waitFor(() => expect(reviewPayloads).toHaveLength(1));
    expect(reviewPayloads[0]).toMatchObject({
      decision: "confirm",
      review_note: "Xác nhận xung đột thời hạn",
      create_amendment_draft: true,
      amendment_action: "modify",
      source_side: "a",
    });
    expect(
      await screen.findByText(/Đã tạo đề xuất sửa đổi ở trạng thái bản nháp \(draft\)/),
    ).toBeInTheDocument();
  });

  it("lists, creates, and updates authority rules in AdminPortal AuthorityRulesPanel", async () => {
    const createdPayloads: Array<Record<string, unknown>> = [];
    const updatedPayloads: Array<Record<string, unknown>> = [];

    const initialRules: AuthorityRuleView[] = [
      {
        id: "rule-1",
        rule_code: "decree_gov",
        doc_type: "decree",
        issuing_body_pattern: "chinh phu",
        authority_rank: 30,
        authority_tier_label: "Nghị định (Chính phủ)",
        is_ambiguous_without_issuer: false,
        match_priority: 10,
        note: "Quy tắc chuẩn",
        is_active: true,
        updated_by: null,
        updated_at: "2026-01-01T00:00:00Z",
      },
      {
        id: "rule-2",
        rule_code: "decision_old",
        doc_type: "decision",
        issuing_body_pattern: null,
        authority_rank: 90,
        authority_tier_label: "Quyết định cũ",
        is_ambiguous_without_issuer: true,
        match_priority: 200,
        note: null,
        is_active: false,
        updated_by: null,
        updated_at: "2026-01-01T00:00:00Z",
      },
    ];

    const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/api/v1/admin/authority-rules/rule-1") && init?.method === "PUT") {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>;
        updatedPayloads.push(body);
        return Promise.resolve(
          new Response(
            JSON.stringify({
              ...initialRules[0],
              authority_rank: Number(body.authority_rank ?? 30),
              authority_tier_label: String(body.authority_tier_label ?? "Nghị định (Chính phủ)"),
            }),
            { status: 200 },
          ),
        );
      }
      if (url.endsWith("/api/v1/admin/authority-rules") && init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>;
        createdPayloads.push(body);
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: "rule-3",
              ...body,
              updated_by: "admin-1",
              updated_at: "2026-01-16T00:00:00Z",
            }),
            { status: 201 },
          ),
        );
      }
      if (url.includes("/api/v1/admin/authority-rules")) {
        const resp: AuthorityRuleListResponse = { total: initialRules.length, items: initialRules };
        return Promise.resolve(new Response(JSON.stringify(resp), { status: 200 }));
      }
      if (url.endsWith("/api/v1/admin/model-registry")) {
        return Promise.resolve(new Response(JSON.stringify({ profiles: [], routes: [] }), { status: 200 }));
      }
      if (url.endsWith("/api/v1/admin/audit-events")) {
        return Promise.resolve(
          new Response(JSON.stringify({ chain: { valid: true, checked: 0 }, events: [] }), { status: 200 }),
        );
      }
      return Promise.resolve(new Response("[]", { status: 200 }));
    });
    vi.stubGlobal("fetch", fetcher);

    render(
      <AdminPortal
        accessToken="admin-token"
        currentUser={{
          id: "admin-1",
          username: "sysadmin",
          display_name: "Quản trị",
          roles: ["SYS_ADMIN"],
          permissions: [],
          must_change_password: false,
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Thứ bậc văn bản" }));

    expect(await screen.findByText("Nghị định (Chính phủ)")).toBeInTheDocument();
    expect(screen.getByText("Đã tắt")).toBeInTheDocument();

    const createForm = screen.getByRole("region", { name: "Thêm quy tắc thứ bậc văn bản" });
    fireEvent.change(within(createForm).getByLabelText("Mã quy tắc"), {
      target: { value: "decision_board" },
    });
    fireEvent.change(within(createForm).getByLabelText("Nhãn bậc hiệu lực hiển thị"), {
      target: { value: "Quyết định Hội đồng" },
    });
    fireEvent.change(within(createForm).getByLabelText("Bậc hiệu lực (1–1000)"), {
      target: { value: "55" },
    });
    fireEvent.click(within(createForm).getByRole("button", { name: "Thêm quy tắc" }));

    await waitFor(() => expect(createdPayloads).toHaveLength(1));
    expect(createdPayloads[0]).toMatchObject({
      rule_code: "decision_board",
      authority_rank: 55,
      authority_tier_label: "Quyết định Hội đồng",
    });

    const editButtons = screen.getAllByRole("button", { name: "Sửa" });
    fireEvent.click(editButtons[0]);

    const editForm = screen.getByRole("form", { name: "Chỉnh sửa quy tắc decree_gov" });
    fireEvent.change(within(editForm).getByLabelText("Sửa bậc hiệu lực (1–1000)"), {
      target: { value: "28" },
    });
    fireEvent.click(within(editForm).getByRole("button", { name: "Lưu thay đổi" }));

    await waitFor(() => expect(updatedPayloads).toHaveLength(1));
    expect(updatedPayloads[0]).toMatchObject({ authority_rank: 28 });
  });

  it("escapes XSS payloads safely without rendering HTML or <img> tags", async () => {
    const xss = "<img src=x onerror=alert(1)>";
    const xssFinding: ConflictFindingView = {
      ...TEST_FINDING_UNDETERMINED,
      node_a_text: `Nội dung A ${xss}`,
      node_b_text: `Nội dung B ${xss}`,
      explanation: `Giải thích ${xss}`,
    };
    const detail = makeScanDetail({ findings: [xssFinding], total_findings: 1 });

    const fetcher = vi.fn().mockImplementation((url: string) => {
      if (url.endsWith("/api/v1/categories")) {
        return Promise.resolve(new Response("[]", { status: 200 }));
      }
      if (url.includes("/api/v1/conflicts/scans?")) {
        return Promise.resolve(new Response(JSON.stringify({ total: 1, items: [detail] }), { status: 200 }));
      }
      if (url.endsWith("/api/v1/conflicts/scans/run-1")) {
        return Promise.resolve(new Response(JSON.stringify(detail), { status: 200 }));
      }
      return Promise.resolve(new Response("{}", { status: 200 }));
    });
    vi.stubGlobal("fetch", fetcher);

    const { container } = render(<ConflictReviewPage accessToken="tok-xss" />);

    fireEvent.click(await screen.findByRole("button", { name: "Xem kết quả" }));
    expect(await screen.findByText(new RegExp(`Nội dung A ${xss.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`))).toBeInTheDocument();
    expect(container.querySelectorAll("img")).toHaveLength(0);
  });

  it("aborts in-flight requests and clears polling timers on unmount without console errors", async () => {
    const capturedSignals: AbortSignal[] = [];
    let pollCalls = 0;
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (init?.signal) capturedSignals.push(init.signal);
      if (url.endsWith("/api/v1/categories")) {
        return Promise.resolve(
          new Response(
            JSON.stringify([
              { id: "cat-1", code: "THUE", name: "Thuế", remote_processing_allowed: false },
            ]),
            { status: 200 },
          ),
        );
      }
      if (url.includes("/api/v1/conflicts/scans?") && (!init?.method || init.method === "GET")) {
        return Promise.resolve(new Response(JSON.stringify({ total: 0, items: [] }), { status: 200 }));
      }
      if (url.endsWith("/api/v1/conflicts/scans") && init?.method === "POST") {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              run_id: "run-unmount",
              status: "queued",
              scope_document_count: 2,
              created_at: "2026-01-15T08:00:00Z",
              deduplicated: false,
            }),
            { status: 202 },
          ),
        );
      }
      if (url.endsWith("/api/v1/conflicts/scans/run-unmount")) {
        pollCalls += 1;
        return Promise.resolve(
          new Response(
            JSON.stringify(
              makeScanDetail({
                id: "run-unmount",
                run_id: "run-unmount",
                status: "running",
                findings: [],
                total_findings: 0,
                summary_json: null,
              }),
            ),
            { status: 200 },
          ),
        );
      }
      return Promise.resolve(new Response("{}", { status: 200 }));
    });
    vi.stubGlobal("fetch", fetcher);

    const { unmount } = render(<ConflictReviewPage accessToken="tok-unmount" />);
    fireEvent.click(screen.getByLabelText("Quét theo 1 danh mục"));
    await waitFor(() => expect(screen.getByRole("option", { name: /Thuế/ })).toBeInTheDocument());

    vi.useFakeTimers();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Bắt đầu rà soát mâu thuẫn" }));
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(pollCalls).toBe(1);
    unmount();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    expect(pollCalls).toBe(1);
    expect(errorSpy).not.toHaveBeenCalled();
    errorSpy.mockRestore();
  });

  it("keeps refreshRecentScans alive after polling transitions to completed so Lượt quét gần đây updates to Hoàn tất", async () => {
    let pollCalls = 0;
    let listCalls = 0;
    let resolveSecondList!: (response: Response) => void;
    const listSignals: AbortSignal[] = [];

    const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      const signal = init?.signal;
      if (url.endsWith("/api/v1/categories")) {
        return Promise.resolve(
          new Response(
            JSON.stringify([
              { id: "cat-1", code: "THUE", name: "Thuế", remote_processing_allowed: false },
            ]),
            { status: 200 },
          ),
        );
      }
      if (url.includes("/api/v1/conflicts/scans?") && (!init?.method || init.method === "GET")) {
        listCalls += 1;
        if (signal) listSignals.push(signal);
        if (listCalls === 1) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                total: 1,
                items: [
                  makeScanDetail({
                    id: "run-refresh",
                    run_id: "run-refresh",
                    status: "running",
                    progress_done: 1,
                  }),
                ],
              }),
              { status: 200 },
            ),
          );
        }
        return new Promise<Response>((resolve, reject) => {
          const rejectIfAborted = () =>
            reject(new DOMException("Aborted", "AbortError"));
          if (signal?.aborted) {
            rejectIfAborted();
            return;
          }
          signal?.addEventListener("abort", rejectIfAborted, { once: true });
          resolveSecondList = (resp) => {
            if (signal?.aborted) {
              rejectIfAborted();
              return;
            }
            resolve(resp);
          };
        });
      }
      if (url.endsWith("/api/v1/conflicts/scans") && init?.method === "POST") {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              run_id: "run-refresh",
              status: "queued",
              scope_document_count: 2,
              created_at: "2026-01-15T08:00:00Z",
              deduplicated: false,
            }),
            { status: 202 },
          ),
        );
      }
      if (url.endsWith("/api/v1/conflicts/scans/run-refresh")) {
        pollCalls += 1;
        return Promise.resolve(
          new Response(
            JSON.stringify(
              makeScanDetail({
                id: "run-refresh",
                run_id: "run-refresh",
                status: pollCalls === 1 ? "running" : "completed",
                progress_done: pollCalls === 1 ? 1 : 4,
              }),
            ),
            { status: 200 },
          ),
        );
      }
      return Promise.resolve(new Response("{}", { status: 200 }));
    });
    vi.stubGlobal("fetch", fetcher);

    render(<ConflictReviewPage accessToken="tok-refresh" />);
    fireEvent.click(screen.getByLabelText("Quét theo 1 danh mục"));
    await waitFor(() => expect(screen.getByRole("option", { name: /Thuế/ })).toBeInTheDocument());

    const recentRegion = await screen.findByRole("region", { name: "Lượt quét gần đây" });
    expect(within(recentRegion).getByText("Đang xử lý")).toBeInTheDocument();

    vi.useFakeTimers();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Bắt đầu rà soát mâu thuẫn" }));
      await Promise.resolve();
      await Promise.resolve();
    });

    // Advance 2000ms -> poll returns completed -> triggers refreshRecentScans & polling useEffect cleanup
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    // Now resolve the in-flight listConflictScans call after React committed the completed state & ran cleanup
    await act(async () => {
      resolveSecondList(
        new Response(
          JSON.stringify({
            total: 1,
            items: [
              makeScanDetail({
                id: "run-refresh",
                run_id: "run-refresh",
                status: "completed",
                progress_done: 4,
              }),
            ],
          }),
          { status: 200 },
        ),
      );
      await Promise.resolve();
      await Promise.resolve();
    });

    const latestRefreshSignal = listSignals[listSignals.length - 1];
    expect(latestRefreshSignal?.aborted).toBe(false);
    expect(within(recentRegion).getByText("Hoàn tất")).toBeInTheDocument();
  });

  it("resets submitting state cleanly when handleSelectScan interrupts an in-flight handleStartScan", async () => {
    let resolveCreate!: (response: Response) => void;
    const pendingCreate = new Promise<Response>((resolve) => {
      resolveCreate = resolve;
    });

    const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.endsWith("/api/v1/categories")) {
        return Promise.resolve(
          new Response(
            JSON.stringify([
              { id: "cat-1", code: "THUE", name: "Thuế", remote_processing_allowed: false },
            ]),
            { status: 200 },
          ),
        );
      }
      if (url.includes("/api/v1/conflicts/scans?") && (!init?.method || init.method === "GET")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              total: 1,
              items: [makeScanDetail({ id: "run-existing", run_id: "run-existing", status: "completed" })],
            }),
            { status: 200 },
          ),
        );
      }
      if (url.endsWith("/api/v1/conflicts/scans") && init?.method === "POST") {
        const signal = init.signal;
        return new Promise<Response>((resolve, reject) => {
          signal?.addEventListener(
            "abort",
            () => reject(new DOMException("Aborted", "AbortError")),
            { once: true },
          );
          void pendingCreate.then(resolve, reject);
        });
      }
      if (url.endsWith("/api/v1/conflicts/scans/run-existing")) {
        return Promise.resolve(
          new Response(
            JSON.stringify(makeScanDetail({ id: "run-existing", run_id: "run-existing", status: "completed" })),
            { status: 200 },
          ),
        );
      }
      return Promise.resolve(new Response("{}", { status: 200 }));
    });
    vi.stubGlobal("fetch", fetcher);

    render(<ConflictReviewPage accessToken="tok-interrupt" />);
    fireEvent.click(screen.getByLabelText("Quét theo 1 danh mục"));
    await waitFor(() => expect(screen.getByRole("option", { name: /Thuế/ })).toBeInTheDocument());
    await screen.findByRole("button", { name: "Xem kết quả" });

    // Start scan (remains in flight)
    fireEvent.click(screen.getByRole("button", { name: "Bắt đầu rà soát mâu thuẫn" }));
    const busyButton = await screen.findByRole("button", { name: "Đang khởi tạo lượt quét…" });
    expect(busyButton).toBeDisabled();

    // Interrupt by clicking "Xem kết quả"
    fireEvent.click(screen.getByRole("button", { name: "Xem kết quả" }));

    const startButton = await screen.findByRole("button", { name: "Bắt đầu rà soát mâu thuẫn" });
    expect(startButton).not.toBeDisabled();

    // Resolve the orphaned create promise just to confirm no late state error occurs
    resolveCreate(
      new Response(
        JSON.stringify({
          run_id: "run-late",
          status: "queued",
          scope_document_count: 2,
          created_at: "2026-01-15T08:00:00Z",
          deduplicated: false,
        }),
        { status: 202 },
      ),
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Bắt đầu rà soát mâu thuẫn" })).not.toBeDisabled(),
    );
  });
});
