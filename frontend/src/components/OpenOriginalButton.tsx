import { useState } from "react";

import { fetchOriginalFile } from "../api/client";
import { SOURCE_FORMAT_LABELS } from "./documentDisplay";

interface OpenOriginalButtonProps {
  url?: string | null;
  accessToken?: string;
  sourceFormat: string;
  page?: number | null;
  label?: string;
  className?: string;
  showHint?: boolean;
}

function saveFile(objectUrl: string, filename: string) {
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  link.remove();
}

/**
 * Opens the imported file itself: a PDF (scans included) in a separate browser tab at
 * the cited page, a Word/TXT file as a download in its own format.  The server checks
 * permission, version and SHA-256 before sending a byte; no OCR or converted copy is used.
 */
export function OpenOriginalButton({
  url, accessToken, sourceFormat, page, label = "Mở văn bản gốc", className, showHint = true,
}: OpenOriginalButtonProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const isPdf = sourceFormat === "pdf";
  const hint = isPdf
    ? page ? `PDF gốc, mở tab mới tại trang ${page}` : "PDF gốc, mở tab mới"
    : `Tải tệp gốc ${SOURCE_FORMAT_LABELS[sourceFormat] ?? sourceFormat}`;

  async function open() {
    if (!url) return;
    setError(undefined);
    setBusy(true);
    // A tab opened inside the click is not blocked; it is filled once the file arrives.
    const tab = isPdf && typeof window.open === "function" ? window.open("", "_blank") : null;
    if (tab) {
      try {
        tab.opener = null;
        tab.document.title = "Đang mở văn bản gốc…";
        tab.document.body.textContent = "Đang mở văn bản gốc…";
      } catch {
        // a browser may refuse to touch the new tab; it is still navigated below
      }
    }
    try {
      const file = await fetchOriginalFile(url, { accessToken });
      const objectUrl = URL.createObjectURL(file.blob);
      if (file.format === "pdf") {
        const target = page && page > 0 ? `${objectUrl}#page=${page}` : objectUrl;
        if (tab && !tab.closed) {
          tab.location.href = target;
        } else if (!window.open(target, "_blank", "noopener")) {
          saveFile(objectUrl, file.filename);
        }
        window.setTimeout(() => URL.revokeObjectURL(objectUrl), 15 * 60_000);
      } else {
        tab?.close();
        saveFile(objectUrl, file.filename);
        window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
      }
    } catch (caught) {
      tab?.close();
      setError(caught instanceof Error ? caught.message : "Không thể mở văn bản gốc.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="open-original">
      <button
        className={className ?? "primary-button open-original-button"}
        disabled={!url || busy || !accessToken}
        onClick={() => void open()}
        title={hint}
        type="button"
      >
        {busy ? "Đang mở…" : label}
      </button>
      {showHint && <small className="open-original-hint">{hint}</small>}
      {error && (
        <small className="open-original-error" role="alert">
          {error}
        </small>
      )}
    </span>
  );
}
