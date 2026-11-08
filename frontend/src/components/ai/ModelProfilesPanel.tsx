import { useState } from "react";

import { testAdminModelProfile } from "../../api/client";
import type { ModelRegistryState } from "../../types";
import {
  STATUS_TEXT,
  describeProfile,
  emptyForm,
  formFromProfile,
  kindOf,
  profileStatus,
  usedBy,
  type ModelCheckResult,
  type ProfileForm,
  type ProfileKind,
  type RegistryProfile,
} from "./aiConfig";
import { CheckResult } from "./CheckResult";
import { ProfileEditor } from "./ProfileEditor";

interface ModelProfilesPanelProps {
  accessToken: string;
  registry: ModelRegistryState;
  onChanged: () => Promise<void>;
  onOpenEmbedding: () => void;
}

const STATUS_CLASS = {
  ready: "status-success", unchecked: "status-warning", error: "status-danger",
  unapproved: "status-warning",
} as const;

function ProfileCard({ profile, registry, checking, check, onCheck, onEdit, onOpenEmbedding }: {
  profile: RegistryProfile;
  registry: ModelRegistryState;
  checking: boolean;
  check?: ModelCheckResult;
  onCheck: () => void;
  onEdit: () => void;
  onOpenEmbedding: () => void;
}) {
  const status = profileStatus(profile);
  const uses = usedBy(registry, profile.profile_id);
  const embedding = profile.capabilities.includes("embedding");
  return (
    <article className="ai-profile" data-kind={kindOf(profile)}>
      <div className="ai-profile-head">
        <div>
          <strong>{profile.profile_id}</strong>
          <span className="evidence-meta"> · {describeProfile(profile)}</span>
        </div>
        <span className={`status-pill ${STATUS_CLASS[status]}`}>{STATUS_TEXT[status]}</span>
      </div>
      <p className="evidence-meta">
        Model <code>{profile.model_id}</code>
        {embedding ? " · tạo vector (embedding)" : ` · ${profile.capabilities.length} chức năng`}
        {uses.length > 0 ? ` · đang dùng cho: ${uses.join("; ")}` : " · chưa được phân công"}
      </p>
      <div className="form-actions">
        <button className="secondary-button" disabled={checking} onClick={onCheck} type="button">
          {checking ? "Đang kiểm tra…" : "Kiểm tra"}
        </button>
        <button className="secondary-button" onClick={onEdit} type="button">Sửa</button>
        {embedding && (
          <button className="secondary-button" onClick={onOpenEmbedding} type="button">
            Quản lý embedding
          </button>
        )}
      </div>
      {check && <CheckResult result={check} title={`Kết quả kiểm tra ${profile.profile_id}`} />}
    </article>
  );
}

/**
 * "Mô hình AI": the saved profiles with their status, and the two forms that add or edit
 * one: AI Local and AI API.  Assigning a model to a function is a separate section.
 */
export function ModelProfilesPanel({
  accessToken, registry, onChanged, onOpenEmbedding,
}: ModelProfilesPanelProps) {
  const [editor, setEditor] = useState<{ form: ProfileForm; key: string } | undefined>();
  const [checks, setChecks] = useState<Record<string, ModelCheckResult>>({});
  const [checking, setChecking] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [error, setError] = useState<string>();
  const secretStore = registry.secret_store?.available ?? false;
  const groups: Array<[ProfileKind, string]> = [["local", "AI Local"], ["api", "AI API"]];

  function open(kind: ProfileKind) {
    setNotice(undefined);
    setEditor({ form: emptyForm(kind), key: `new-${kind}-${Date.now()}` });
  }

  async function check(profile: RegistryProfile) {
    setChecking(profile.profile_id);
    setError(undefined);
    try {
      const result = await testAdminModelProfile(accessToken, profile.profile_id);
      setChecks((current) => ({ ...current, [profile.profile_id]: result }));
      await onChanged();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Không kiểm tra được hồ sơ.");
    } finally {
      setChecking(undefined);
    }
  }

  return (
    <div className="admin-grid ai-grid" aria-label="Mô hình AI">
      <section className="admin-card">
        <div className="admin-card-title-row">
          <h2>Mô hình AI ({registry.profiles.length})</h2>
          <div className="form-actions">
            <button className="primary-button" onClick={() => open("local")} type="button">
              Thêm AI Local
            </button>
            <button className="primary-button" onClick={() => open("api")} type="button">
              Thêm AI API
            </button>
          </div>
        </div>
        {notice && <p className="status-pill status-success" role="status">{notice}</p>}
        {error && <p className="status-pill status-danger" role="alert">{error}</p>}
        {registry.profiles.length === 0 && (
          <p className="evidence-meta">
            Chưa có mô hình nào. Thêm một AI Local (chạy trên máy này hoặc máy chủ nội bộ) hoặc
            một AI API (dịch vụ trên Internet).
          </p>
        )}
        {groups.map(([kind, title]) => {
          const profiles = registry.profiles.filter((item) => kindOf(item) === kind);
          return profiles.length === 0 ? null : (
            <div className="ai-profile-group" key={kind}>
              <h3>{title}</h3>
              {profiles.map((profile) => (
                <ProfileCard
                  check={checks[profile.profile_id]}
                  checking={checking === profile.profile_id}
                  key={profile.profile_id}
                  onCheck={() => void check(profile)}
                  onEdit={() => {
                    setNotice(undefined);
                    setEditor({ form: formFromProfile(profile), key: `edit-${profile.profile_id}` });
                  }}
                  onOpenEmbedding={onOpenEmbedding}
                  profile={profile}
                  registry={registry}
                />
              ))}
            </div>
          );
        })}
      </section>

      {editor && (
        <section className="admin-card">
          <h2>
            {editor.form.editing ? `Sửa ${editor.form.name}` : editor.form.kind === "local"
              ? "Thêm AI Local" : "Thêm AI API"}
          </h2>
          <ProfileEditor
            accessToken={accessToken}
            initial={editor.form}
            key={editor.key}
            onCancel={() => setEditor(undefined)}
            onSaved={async (message) => {
              setEditor(undefined);
              setNotice(message);
              await onChanged();
            }}
            secretStoreAvailable={secretStore}
          />
        </section>
      )}
    </div>
  );
}
