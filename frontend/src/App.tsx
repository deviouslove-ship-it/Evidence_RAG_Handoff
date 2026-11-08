import { useCallback, useEffect, useState } from "react";

import { changePassword, getSystemMode, logoutSession } from "./api/client";
import { DesktopOrb } from "./components/DesktopOrb";
import { LoginPanel } from "./components/LoginPanel";
import {
  invokeDesktop,
  isOrbDesktopWindow,
  isTauriDesktop,
  listenDesktopLogout,
  listenOrbWorkspaceSync,
} from "./desktop/bridge";
import { AdminPortal } from "./pages/AdminPortal";
import { EvidenceChat, type ExternalWorkspaceSync } from "./pages/EvidenceChat";
import { SearchPage } from "./pages/SearchPage";
import type { QueryResponse, UserInfo } from "./types";

const ADMIN_ROLES = new Set(["CURATOR", "REVIEWER", "SYS_ADMIN", "AUDITOR"]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isQueryResponsePayload(value: unknown): value is QueryResponse {
  if (!isRecord(value) || !Array.isArray(value.evidence) || !Array.isArray(value.claims)) {
    return false;
  }
  const evidenceValid = value.evidence.every(
    (item) =>
      isRecord(item) &&
      typeof item.evidence_id === "string" &&
      typeof item.title === "string" &&
      typeof item.label === "string" &&
      typeof item.quote_exact === "string" &&
      typeof item.viewer_url === "string",
  );
  const claimsValid = value.claims.every(
    (item) =>
      isRecord(item) &&
      typeof item.text === "string" &&
      Array.isArray(item.evidence_ids) &&
      item.evidence_ids.every((evidenceId) => typeof evidenceId === "string"),
  );
  return evidenceValid && claimsValid;
}

/** A shared search link (?q=…) opens the search page; everything else starts in Hỏi đáp. */
function initialUserView(): "chat" | "search" {
  if (typeof window === "undefined") return "chat";
  try {
    return new URLSearchParams(window.location.search).get("q") ? "search" : "chat";
  } catch {
    return "chat";
  }
}

export default function App() {
  const [hash, setHash] = useState(() =>
    typeof window !== "undefined" ? window.location.hash : "",
  );
  const [mode, setMode] = useState<string>();
  const [session, setSession] = useState<{ accessToken: string; user: UserInfo }>();
  const [showLogin, setShowLogin] = useState(false);
  const [showChangePassword, setShowChangePassword] = useState(false);
  const [cpCurrent, setCpCurrent] = useState("");
  const [cpNew, setCpNew] = useState("");
  const [cpConfirm, setCpConfirm] = useState("");
  const [cpMessage, setCpMessage] = useState<string>();
  const [cpError, setCpError] = useState<string>();
  const [surface, setSurface] = useState<"user" | "admin">("user");
  // One search page ("Tìm kiếm văn bản", built on the comprehensive search); the former
  // "Tìm toàn diện" view is merged into it.
  const [userView, setUserView] = useState<"chat" | "search">(initialUserView);
  const [searchQuery, setSearchQuery] = useState<string>();
  const [alwaysOnTop, setAlwaysOnTop] = useState(false);
  const [externalSync, setExternalSync] = useState<ExternalWorkspaceSync>();
  const [desktopError, setDesktopError] = useState<string>();

  useEffect(() => {
    const onHash = () => setHash(window.location.hash);
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const isOrbWindow = hash === "#/orb" || isOrbDesktopWindow();

  useEffect(() => {
    if (isOrbWindow) {
      document.documentElement.classList.add("orb-window");
      document.body.classList.add("orb-window");
      return () => {
        document.documentElement.classList.remove("orb-window");
        document.body.classList.remove("orb-window");
      };
    }
    return undefined;
  }, [isOrbWindow]);

  useEffect(() => {
    if (isOrbWindow) return undefined;
    let active = true;
    getSystemMode().then(
      (response) => {
        if (active) setMode(response.effective_mode);
      },
      () => {
        if (active) setMode("unknown");
      },
    );
    return () => {
      active = false;
    };
  }, [isOrbWindow]);

  const handleLogout = useCallback(async () => {
    const token = session?.accessToken;
    setSession(undefined);
    setSurface("user");
    setUserView("chat");
    setSearchQuery(undefined);
    setShowLogin(false);
    setExternalSync(undefined);
    setDesktopError(undefined);
    await invokeDesktop("session_ended");
    if (token) {
      try {
        await logoutSession(token);
      } catch {
        // Ignore network failure during logout; local state is already cleared.
      }
    }
  }, [session?.accessToken]);

  const openSearch = useCallback((query?: string) => {
    const trimmed = query?.trim();
    setSearchQuery(trimmed ? trimmed : undefined);
    setUserView("search");
  }, []);

  useEffect(() => {
    if (isOrbWindow) return undefined;
    return listenDesktopLogout(() => {
      void handleLogout();
    });
  }, [handleLogout, isOrbWindow]);

  useEffect(() => {
    if (isOrbWindow || !session) return undefined;
    return listenOrbWorkspaceSync((payload) => {
      const response = payload.response;
      if (!isQueryResponsePayload(response)) return;
      const payloadUserId = typeof payload.userId === "string" ? payload.userId : undefined;
      if (!payloadUserId || payloadUserId !== session.user.id) return;
      const selectedId =
        isRecord(payload.selected) && typeof payload.selected.evidence_id === "string"
          ? payload.selected.evidence_id
          : undefined;
      const selected = response.evidence.find((item) => item.evidence_id === selectedId);
      const question = typeof payload.question === "string" ? payload.question : undefined;
      setSurface("user");
      setExternalSync((prev) => ({
        response,
        selected,
        question,
        accessToken: undefined,
        seq: (prev?.seq ?? 0) + 1,
      }));
    });
  }, [isOrbWindow, session]);

  if (isOrbWindow) {
    return <DesktopOrb />;
  }

  const modeLabel =
    mode === "API"
      ? "Chế độ API"
      : mode === "LOCAL"
        ? "Chế độ Local"
        : mode === undefined
          ? "Đang kiểm tra chế độ…"
          : "Chưa xác nhận chế độ";

  const canOpenAdmin = Boolean(
    session?.user.roles.some((role) => ADMIN_ROLES.has(role)),
  );
  const canQuery = !session || session.user.roles.includes("USER");

  async function onAuthenticated(next: { accessToken: string; user: UserInfo }) {
    setSession(next);
    setShowLogin(false);
    setUserView(initialUserView());
    setSearchQuery(undefined);
    setExternalSync(undefined);
    setDesktopError(undefined);
    const hasAdmin = next.user.roles.some((r) => ADMIN_ROLES.has(r));
    const hasUser = next.user.roles.includes("USER");
    setSurface(!hasUser && hasAdmin ? "admin" : "user");
    if (!(await invokeDesktop("session_started"))) {
      setDesktopError("Không thể khởi tạo cửa sổ desktop cho phiên hiện tại.");
    }
  }

  async function toggleAlwaysOnTop(next: boolean) {
    setDesktopError(undefined);
    if (await invokeDesktop("set_always_on_top", { alwaysOnTop: next })) {
      setAlwaysOnTop(next);
    } else {
      setDesktopError("Không thể cập nhật tùy chọn ghim nổi.");
    }
  }

  async function handleTopbarChangePassword(event: React.FormEvent) {
    event.preventDefault();
    if (!session) return;
    setCpError(undefined);
    setCpMessage(undefined);
    if (cpNew.length < 12) {
      setCpError("Mật khẩu mới phải có tối thiểu 12 ký tự.");
      return;
    }
    if (cpNew !== cpConfirm) {
      setCpError("Xác nhận mật khẩu mới không khớp.");
      return;
    }
    try {
      await changePassword(session.accessToken, cpCurrent, cpNew);
      setCpCurrent("");
      setCpNew("");
      setCpConfirm("");
      setCpMessage("Đã đổi mật khẩu thành công.");
    } catch (caught) {
      setCpError(caught instanceof Error ? caught.message : "Không thể đổi mật khẩu.");
    }
  }

  return (
    <div className="app-shell">
      <header className="app-topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            §
          </span>
          <div className="brand-text">
            <strong>Hệ thống Tra cứu Pháp lý</strong>
            <small>Hỏi đáp tiếng Việt có căn cứ xác thực</small>
          </div>
        </div>
        <div className="topbar-controls">
          {canQuery && surface !== "admin" && (
            <nav aria-label="Khu vực tra cứu" className="surface-switch">
              <button
                aria-current={userView === "chat" ? "page" : undefined}
                className={userView === "chat" ? "topbar-button active" : "topbar-button"}
                onClick={() => setUserView("chat")}
                type="button"
              >
                Hỏi đáp
              </button>
              <button
                aria-current={userView === "search" ? "page" : undefined}
                className={userView === "search" ? "topbar-button active" : "topbar-button"}
                onClick={() => openSearch()}
                type="button"
              >
                Tìm kiếm văn bản
              </button>
            </nav>
          )}
          {session && canOpenAdmin && canQuery && (
            <div className="surface-switch" role="group" aria-label="Chuyển cổng làm việc">
              <button
                className={surface === "user" ? "topbar-button active" : "topbar-button"}
                onClick={() => setSurface("user")}
                type="button"
              >
                Không gian tra cứu
              </button>
              <button
                aria-label="Admin Portal"
                className={surface === "admin" ? "topbar-button active" : "topbar-button"}
                onClick={() => setSurface("admin")}
                type="button"
              >
                Cổng quản trị
              </button>
            </div>
          )}
          {isTauriDesktop() && (
            <label className="topbar-toggle">
              <input
                checked={alwaysOnTop}
                onChange={(e) => void toggleAlwaysOnTop(e.target.checked)}
                type="checkbox"
              />
              <span>Ghim nổi</span>
            </label>
          )}
          <span className="mode-badge" title="Chế độ vận hành hiện tại của máy chủ">
            {modeLabel}
          </span>
          {session ? (
            <div className="session-bar">
              <span className="user-pill" title={session.user.roles.join(", ")}>
                {session.user.display_name} ({session.user.username})
              </span>
              <button
                className="topbar-button"
                onClick={() => {
                  setCpError(undefined);
                  setCpMessage(undefined);
                  setShowChangePassword((prev) => !prev);
                }}
                type="button"
              >
                Đổi mật khẩu
              </button>
              <button
                className="topbar-button"
                onClick={() => void handleLogout()}
                type="button"
              >
                Đăng xuất
              </button>
            </div>
          ) : (
            <button
              className="topbar-button"
              onClick={() => setShowLogin((prev) => !prev)}
              type="button"
            >
              {showLogin ? "Đóng đăng nhập" : "Đăng nhập"}
            </button>
          )}
        </div>
      </header>
      <main className="app-main">
        {desktopError && (
          <p className="status-pill status-danger admin-alert" role="alert">
            {desktopError}
          </p>
        )}
        {showLogin && !session && (
          <div
            className="login-backdrop"
            onClick={(event) => {
              if (event.target === event.currentTarget) {
                setShowLogin(false);
              }
            }}
          >
            <LoginPanel
              onAuthenticated={(next) => void onAuthenticated(next)}
              onCancel={() => setShowLogin(false)}
            />
          </div>
        )}
        {showChangePassword && session && (
          <div
            className="login-backdrop"
            onClick={(event) => {
              if (event.target === event.currentTarget) {
                setShowChangePassword(false);
              }
            }}
          >
            <section className="login-panel" aria-label="Đổi mật khẩu tài khoản">
              <h2>Đổi mật khẩu tài khoản ({session.user.username})</h2>
              <p>Nhập mật khẩu hiện tại và mật khẩu mới (tối thiểu 12 ký tự).</p>
              {cpMessage && <div className="admin-banner status">{cpMessage}</div>}
              {cpError && <div className="admin-banner error">{cpError}</div>}
              <form className="form-stack" onSubmit={handleTopbarChangePassword}>
                <label className="field-label">
                  Mật khẩu hiện tại
                  <input
                    onChange={(e) => setCpCurrent(e.target.value)}
                    required
                    type="password"
                    value={cpCurrent}
                  />
                </label>
                <label className="field-label">
                  Mật khẩu mới (≥ 12 ký tự)
                  <input
                    onChange={(e) => setCpNew(e.target.value)}
                    required
                    type="password"
                    value={cpNew}
                  />
                </label>
                <label className="field-label">
                  Xác nhận mật khẩu mới
                  <input
                    onChange={(e) => setCpConfirm(e.target.value)}
                    required
                    type="password"
                    value={cpConfirm}
                  />
                </label>
                <div className="form-actions">
                  <button className="primary-button" type="submit">
                    Lưu mật khẩu mới
                  </button>
                  <button
                    className="secondary-button"
                    onClick={() => setShowChangePassword(false)}
                    type="button"
                  >
                    Đóng
                  </button>
                </div>
              </form>
            </section>
          </div>
        )}
        {session && surface === "admin" && canOpenAdmin ? (
          <AdminPortal accessToken={session.accessToken} currentUser={session.user} />
        ) : (
          <>
            <div className="user-view" hidden={userView !== "chat"}>
              <EvidenceChat
                accessToken={session?.accessToken}
                externalSync={externalSync}
                onViewAllResults={openSearch}
                operatingMode={mode}
              />
            </div>
            {userView === "search" && (
              <div className="user-view">
                <SearchPage accessToken={session?.accessToken} initialQuery={searchQuery} />
              </div>
            )}

          </>
        )}
      </main>
    </div>
  );
}
