import { useState } from "react";
import { changePassword, loginWithPassword } from "../api/client";
import { isTauriDesktop } from "../desktop/bridge";
import type { LoginResponse, UserInfo } from "../types";

interface LoginPanelProps {
  onAuthenticated: (session: { accessToken: string; user: UserInfo }) => void;
  onCancel?: () => void;
}

export function LoginPanel({ onAuthenticated, onCancel }: LoginPanelProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [pendingSession, setPendingSession] = useState<LoginResponse>();
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  async function submitLogin(event: React.FormEvent) {
    event.preventDefault();
    if (!username.trim() || !password) return;
    setBusy(true);
    setError(undefined);
    try {
      const response = await loginWithPassword(
        username.trim(),
        password,
        isTauriDesktop() ? "desktop" : "web",
      );
      if (response.user.must_change_password) {
        setPendingSession(response);
      } else {
        onAuthenticated({ accessToken: response.access_token, user: response.user });
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Không thể đăng nhập.");
    } finally {
      setBusy(false);
    }
  }

  async function submitPasswordChange(event: React.FormEvent) {
    event.preventDefault();
    if (!pendingSession) return;
    if (newPassword !== confirmPassword) {
      setError("Mật khẩu xác nhận không khớp.");
      return;
    }
    setBusy(true);
    setError(undefined);
    try {
      await changePassword(pendingSession.access_token, password, newPassword);
      onAuthenticated({
        accessToken: pendingSession.access_token,
        user: { ...pendingSession.user, must_change_password: false },
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Không thể đổi mật khẩu.");
    } finally {
      setBusy(false);
    }
  }

  if (pendingSession) {
    return (
      <section className="login-dialog" aria-label="Đổi mật khẩu lần đầu">
        <h2>Đổi mật khẩu bắt buộc</h2>
        <p>
          Tài khoản <strong>{pendingSession.user.username}</strong> cần đổi mật khẩu (tối thiểu 12 ký
          tự) trước khi tra cứu hoặc quản trị.
        </p>
        <form onSubmit={submitPasswordChange} className="form-stack">
          <label className="field-label">
            Mật khẩu mới
            <input
              aria-label="Mật khẩu mới"
              autoComplete="new-password"
              onChange={(event) => setNewPassword(event.target.value)}
              required
              type="password"
              value={newPassword}
            />
          </label>
          <label className="field-label">
            Nhập lại mật khẩu mới
            <input
              aria-label="Nhập lại mật khẩu mới"
              autoComplete="new-password"
              onChange={(event) => setConfirmPassword(event.target.value)}
              required
              type="password"
              value={confirmPassword}
            />
          </label>
          <div className="form-actions">
            <button className="primary-button" disabled={busy} type="submit">
              {busy ? "Đang cập nhật…" : "Lưu mật khẩu & tiếp tục"}
            </button>
          </div>
          {error && (
            <p className="status-pill status-danger" role="alert">
              {error}
            </p>
          )}
        </form>
      </section>
    );
  }

  return (
    <section className="login-dialog" aria-label="Đăng nhập hệ thống">
      <h2>Đăng nhập Evidence RAG</h2>
      <p>Sử dụng tài khoản nội bộ để mở phiên tra cứu có kiểm soát quyền truy cập.</p>
      <form onSubmit={submitLogin} className="form-stack">
        <label className="field-label">
          Tên đăng nhập
          <input
            aria-label="Tên đăng nhập"
            autoComplete="username"
            onChange={(event) => setUsername(event.target.value)}
            required
            type="text"
            value={username}
          />
        </label>
        <label className="field-label">
          Mật khẩu
          <input
            aria-label="Mật khẩu"
            autoComplete="current-password"
            onChange={(event) => setPassword(event.target.value)}
            required
            type="password"
            value={password}
          />
        </label>
        <div className="form-actions">
          {onCancel && (
            <button className="secondary-button" onClick={onCancel} type="button">
              Đóng
            </button>
          )}
          <button
            className="primary-button"
            disabled={busy || !username.trim() || !password}
            type="submit"
          >
            {busy ? "Đang xác thực…" : "Đăng nhập"}
          </button>
        </div>
        {error && (
          <p className="status-pill status-danger" role="alert">
            {error}
          </p>
        )}
      </form>
    </section>
  );
}
