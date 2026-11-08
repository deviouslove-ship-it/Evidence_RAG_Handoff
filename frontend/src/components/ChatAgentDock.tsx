import { useEffect, useRef, useState } from "react";
import {
  loginWithPassword,
  queryEvidence,
} from "../api/client";
import {
  invokeDesktop,
  listenDesktopLogout,
  readDesktopSessionActive,
} from "../desktop/bridge";
import type { EvidenceRef, QueryResponse, UserInfo } from "../types";
import { localDateISO } from "../localDate";
import { SAMPLE_PROMPTS } from "../samplePrompts";

const DOCK_STATUS_LABELS: Record<string, string> = {
  evidence_found: "đã tìm thấy căn cứ",
  conditional: "có căn cứ, cần đối chiếu hiệu lực và điều kiện áp dụng",
  insufficient: "chưa đủ căn cứ",
  conflicting: "các căn cứ có điểm mâu thuẫn",
};

interface ChatAgentDockProps {
  accessToken?: string;
  standaloneDesktop?: boolean;
  onOpenInWorkspace?: (
    response: QueryResponse,
    selected?: EvidenceRef,
    question?: string,
    agentToken?: string,
  ) => void;
}


export function ChatAgentDock({
  accessToken,
  standaloneDesktop = false,
  onOpenInWorkspace,
}: ChatAgentDockProps) {
  const [open, setOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [lastQuestion, setLastQuestion] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [response, setResponse] = useState<QueryResponse>();
  const [agentSession, setAgentSession] = useState<{
    accessToken: string;
    user: UserInfo;
  }>();
  const [showInlineAuth, setShowInlineAuth] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [authBusy, setAuthBusy] = useState(false);
  const [nativeSessionActive, setNativeSessionActive] = useState<boolean>();
  const abortRef = useRef<AbortController | null>(null);

  const effectiveToken = accessToken ?? agentSession?.accessToken;

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (standaloneDesktop) return;
    abortRef.current?.abort();
    setAgentSession(undefined);
    setResponse(undefined);
    setLastQuestion(undefined);
    setError(undefined);
  }, [accessToken, standaloneDesktop]);

  useEffect(() => {
    if (!standaloneDesktop) return undefined;
    let active = true;
    void readDesktopSessionActive().then((value) => {
      if (active) setNativeSessionActive(value);
    });
    return () => {
      active = false;
    };
  }, [standaloneDesktop]);

  useEffect(() => {
    return listenDesktopLogout(() => {
      abortRef.current?.abort();
      setAgentSession(undefined);
      setNativeSessionActive(false);
      setResponse(undefined);
      setLastQuestion(undefined);
      setPrompt("");
      setShowInlineAuth(false);
      setOpen(false);
      setError("Phiên đăng nhập đã kết thúc. Hãy đăng nhập lại để tra cứu.");
    });
  }, []);

  function toggleOpen(nextState?: boolean) {
    const target = nextState ?? !open;
    setOpen(target);
    if (standaloneDesktop) {
      void invokeDesktop("set_orb_expanded", { expanded: target });
    }
  }

  function syncToMainWorkspace(
    res: QueryResponse,
    selected?: EvidenceRef,
    question?: string,
    tokenToUse?: string,
  ) {
    if (onOpenInWorkspace) {
      onOpenInWorkspace(res, selected, question, tokenToUse);
    }
    if (standaloneDesktop) {
      void invokeDesktop("open_workspace_from_orb", {
        payload: {
          response: res,
          selected: selected ?? res.evidence[0],
          question,
          accessToken: tokenToUse,
          userId: agentSession?.user.id,
        },
      });
    }
  }

  async function askAgent(textToAsk: string) {
    const clean = textToAsk.trim();
    if (!clean) return;
    if (!effectiveToken) {
      setShowInlineAuth(true);
      setError("Hãy đăng nhập tài khoản để tra cứu bằng Orb.");
      return;
    }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLastQuestion(clean);
    setBusy(true);
    setError(undefined);
    try {
      const today = localDateISO();
      const res = await queryEvidence(
        {
          question: clean,
          facts: [],
          scope: {
            scope_mode: "ALL_AUTHORIZED",
            category_ids: [],
            document_types: [],
            as_of_date: today,
          },
        },
        { accessToken: effectiveToken, signal: controller.signal },
      );
      if (abortRef.current !== controller) return;
      setResponse(res);
      setPrompt("");
      if (onOpenInWorkspace) {
        onOpenInWorkspace(res, res.evidence[0], clean, effectiveToken);
      }
    } catch (caught) {
      if (abortRef.current !== controller) return;
      if (controller.signal.aborted) {
        setError("Đã dừng lượt tra cứu Agent.");
      } else {
        setError(caught instanceof Error ? caught.message : "Không thể tra cứu lúc này.");
      }
    } finally {
      if (abortRef.current === controller) {
        setBusy(false);
      }
    }
  }

  function stopAgentQuery() {
    abortRef.current?.abort();
    setBusy(false);
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    void askAgent(prompt);
  }

  async function handleInlineLogin(event: React.FormEvent) {
    event.preventDefault();
    if (!username.trim() || !password) return;
    setAuthBusy(true);
    setError(undefined);
    try {
      const loggedIn = await loginWithPassword(username.trim(), password, "desktop");
      setAgentSession({
        accessToken: loggedIn.access_token,
        user: loggedIn.user,
      });
      if (standaloneDesktop) {
        if (!(await invokeDesktop("session_started"))) {
          setAgentSession(undefined);
          setNativeSessionActive(false);
          setError("Không thể kích hoạt phiên desktop cho tài khoản này.");
          return;
        }
        setNativeSessionActive(true);
      }
      setPassword("");
      setShowInlineAuth(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Đăng nhập Agent thất bại.");
    } finally {
      setAuthBusy(false);
    }
  }

  return (
    <aside
      className={standaloneDesktop ? "chat-agent-dock standalone-orb-dock" : "chat-agent-dock"}
      aria-label="Trợ lý nổi Chat Agent"
    >
      {open && (
        <section className="chat-agent-drawer" aria-label="Khung hỏi đáp nhanh Chat Agent">
          <header className="chat-agent-header">
            <div className="chat-agent-title">
              <span className="chat-agent-avatar" aria-hidden="true">
                <svg fill="none" height="18" viewBox="0 0 24 24" width="18">
                  <path
                    d="M12 3C7.03 3 3 6.58 3 11c0 2.07.89 3.96 2.36 5.38L4 21l4.86-1.58c1 .37 2.09.58 3.14.58 4.97 0 9-3.58 9-8s-4.03-8-9-8Z"
                    stroke="currentColor"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="1.9"
                  />
                  <path
                    d="M12 7.5 13.1 10l2.65 1.1-2.65 1.1L12 14.8l-1.1-2.6-2.65-1.1 2.65-1.1L12 7.5Z"
                    fill="currentColor"
                  />
                </svg>
              </span>
              <div>
                <strong>Chat Agent AI</strong>
                <small>Tra cứu theo phiên đăng nhập và quyền tài khoản</small>
              </div>
            </div>
            <div className="chat-agent-header-actions">
              <button
                className="chat-agent-icon-btn"
                onClick={() => setShowInlineAuth((prev) => !prev)}
                title="Chuyển tài khoản trực tiếp trên Agent"
                type="button"
              >
                {agentSession?.user?.username ?? "Đăng nhập"}
              </button>
              <button
                aria-label="Đóng khung Chat Agent"
                className="chat-agent-icon-btn"
                onClick={() => toggleOpen(false)}
                title="Thu gọn"
                type="button"
              >
                ✕
              </button>
            </div>
          </header>

          <div className="chat-agent-body">
            <div className="chat-agent-status-bar">
              <span className="chat-agent-status-dot" aria-hidden="true" />
              <span>
                {standaloneDesktop && nativeSessionActive === false && !effectiveToken
                  ? "Cần đăng nhập để kích hoạt phiên desktop"
                  : effectiveToken
                  ? "Đã đăng nhập · Tra cứu theo quyền tài khoản"
                  : "Cần đăng nhập tài khoản trước khi tra cứu"}
              </span>
            </div>

            {(showInlineAuth || !effectiveToken) && (
              <form className="chat-agent-inline-auth" onSubmit={handleInlineLogin}>
                <div className="chat-agent-inline-auth-row">
                  <input
                    aria-label="Tên tài khoản Agent"
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="Tài khoản (vd: chuyenvien)"
                    type="text"
                    value={username}
                  />
                  <input
                    aria-label="Mật khẩu Agent"
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Mật khẩu"
                    type="password"
                    value={password}
                  />
                </div>
                <div className="chat-agent-inline-auth-actions">
                  <button
                    className="secondary-button"
                    onClick={() => setShowInlineAuth(false)}
                    type="button"
                  >
                    Đóng
                  </button>
                  <button
                    className="primary-button"
                    disabled={authBusy || !username.trim() || !password}
                    type="submit"
                  >
                    {authBusy ? "Đang xác thực…" : "Đăng nhập"}
                  </button>
                </div>
              </form>
            )}

            <div className="chat-agent-samples" aria-label="Câu hỏi gợi ý">
              <span className="chat-agent-samples-label">Gợi ý tra cứu nhanh:</span>
              <div className="chat-agent-sample-list">
                {SAMPLE_PROMPTS.map((item) => (
                  <button
                    className="chat-agent-sample-chip"
                    disabled={busy}
                    key={item}
                    onClick={() => void askAgent(item)}
                    type="button"
                  >
                    {item}
                  </button>
                ))}
              </div>
            </div>

            {lastQuestion && (
              <div className="chat-agent-bubble chat-agent-bubble-user">
                <small>Câu hỏi vừa gửi</small>
                <p>{lastQuestion}</p>
              </div>
            )}

            {error && (
              <p className="status-pill status-danger" role="alert">
                {error}
              </p>
            )}

            {response && (
              <div className="chat-agent-bubble chat-agent-bubble-agent">
                <small>
                  Kết quả ({response.evidence.length} căn cứ nguồn)
                </small>
                {response.status && (
                  <p className="evidence-meta">
                    Trạng thái: {DOCK_STATUS_LABELS[response.status] ?? response.status}
                  </p>
                )}
                {response.answer ? (
                  <p className="chat-agent-claim">{response.answer.summary}</p>
                ) : response.claims.length > 0 ? (
                  <p className="chat-agent-claim">{response.claims[0].text}</p>
                ) : (
                  <p className="chat-agent-claim">
                    Chưa tìm thấy điều khoản khớp trực tiếp trong phạm vi hiện tại.
                  </p>
                )}
                {response.disclaimer && <p className="evidence-meta">{response.disclaimer}</p>}
                {response.evidence.length > 0 && (
                  <div className="chat-agent-citations">
                    {response.evidence.slice(0, 4).map((ev, idx) => (
                      <button
                        className="chat-agent-citation-btn"
                        key={ev.evidence_id}
                        onClick={() =>
                          syncToMainWorkspace(response, ev, lastQuestion, effectiveToken)
                        }
                        type="button"
                      >
                        <strong>
                          [{idx + 1}] {ev.document_number ?? "Văn bản"} · {ev.label}
                        </strong>
                        <span>Trang {ev.page ?? 1} — Mở PDF nguồn</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          <form className="chat-agent-footer" onSubmit={handleSubmit}>
            <input
              aria-label="Nhập câu hỏi cho Chat Agent"
              disabled={busy}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="Nhập câu hỏi pháp lý cần tra cứu…"
              type="text"
              value={prompt}
            />
            {busy ? (
              <button
                className="secondary-button"
                onClick={stopAgentQuery}
                type="button"
              >
                Dừng
              </button>
            ) : (
              <button
                className="primary-button"
                disabled={!prompt.trim()}
                type="submit"
              >
                Hỏi Agent
              </button>
            )}
          </form>
        </section>
      )}

      <button
        aria-expanded={open}
        aria-label={
          standaloneDesktop
            ? "Mở hoặc thu trợ lý Evidence RAG"
            : "Mở hoặc đóng trợ lý Chat Agent"
        }
        className={open ? "chat-agent-fab active" : "chat-agent-fab"}
        onClick={() => toggleOpen()}
        title="Chat Agent độc lập · Vị trí cố định góc phải màn hình"
        type="button"
      >
        <span className="chat-agent-fab-halo" aria-hidden="true" />
        <span className="chat-agent-fab-icon" aria-hidden="true">
          <svg fill="none" height="28" viewBox="0 0 24 24" width="28">
            <path
              d="M12 3C6.75 3 2.5 6.82 2.5 11.5c0 2.25.98 4.3 2.58 5.82L3.6 21.4l4.75-1.63c1.14.47 2.38.73 3.65.73 5.25 0 9.5-3.82 9.5-8.5S17.25 3 12 3Z"
              fill="rgba(255, 255, 255, 0.16)"
              stroke="currentColor"
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="1.85"
            />
            <path
              d="M12 7.2 13.25 10l2.85 1.25-2.85 1.25L12 15.35 10.75 12.5 7.9 11.25 10.75 10 12 7.2Z"
              fill="currentColor"
            />
            <circle cx="16.8" cy="7.8" fill="currentColor" r="1.15" />
          </svg>
        </span>
        <span className="chat-agent-fab-dot" aria-hidden="true" />
      </button>
    </aside>
  );
}
