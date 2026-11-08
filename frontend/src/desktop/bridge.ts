interface TauriGlobal {
  core?: {
    invoke: (command: string, args?: Record<string, unknown>) => Promise<unknown>;
  };
  window?: {
    getCurrentWindow: () => {
      label?: string;
    };
  };
  event?: {
    listen: (
      eventName: string,
      handler: (event: { payload?: unknown }) => void,
    ) => Promise<() => void>;
  };
}

function getTauri(): TauriGlobal | undefined {
  if (typeof window === "undefined") return undefined;
  return (window as unknown as { __TAURI__?: TauriGlobal }).__TAURI__;
}

export function isTauriDesktop(): boolean {
  return Boolean(getTauri()?.core?.invoke);
}

export function isOrbDesktopWindow(): boolean {
  if (typeof window === "undefined") return false;
  if (window.location.hash === "#/orb") return true;
  const label = getTauri()?.window?.getCurrentWindow?.()?.label;
  if (label === "orb") return true;
  const internals = (
    window as unknown as {
      __TAURI_INTERNALS__?: { metadata?: { currentWindow?: { label?: string } } };
    }
  ).__TAURI_INTERNALS__;
  return internals?.metadata?.currentWindow?.label === "orb";
}

export async function invokeDesktop(
  command: string,
  args?: Record<string, unknown>,
): Promise<boolean> {
  const invoke = getTauri()?.core?.invoke;
  if (!invoke) return true;
  try {
    await invoke(command, args);
    return true;
  } catch {
    return false;
  }
}

export async function readDesktopSessionActive(): Promise<boolean | undefined> {
  const invoke = getTauri()?.core?.invoke;
  if (!invoke) return undefined;
  try {
    const active = await invoke("session_active");
    return active === true;
  } catch {
    return undefined;
  }
}

export function listenDesktopLogout(onLogout: () => void): () => void {
  let disposed = false;
  let unlisten: (() => void) | undefined;
  const handler = () => onLogout();
  window.addEventListener("evidence:logout", handler);
  const tauriListen = getTauri()?.event?.listen;
  if (tauriListen) {
    void tauriListen("evidence-logout-requested", () => onLogout())
      .then((fn) => {
        if (disposed) {
          fn();
        } else {
          unlisten = fn;
        }
      })
      .catch(() => undefined);
  }
  return () => {
    disposed = true;
    window.removeEventListener("evidence:logout", handler);
    if (unlisten) unlisten();
  };
}

export function listenOrbWorkspaceSync(
  onSync: (payload: Record<string, unknown>) => void,
): () => void {
  let disposed = false;
  let unlisten: (() => void) | undefined;
  const tauriListen = getTauri()?.event?.listen;
  if (tauriListen) {
    void tauriListen("evidence-sync-from-orb", (event) => {
      if (event && typeof event.payload === "object" && event.payload !== null) {
        onSync(event.payload as Record<string, unknown>);
      }
    })
      .then((fn) => {
        if (disposed) {
          fn();
        } else {
          unlisten = fn;
        }
      })
      .catch(() => undefined);
  }
  return () => {
    disposed = true;
    if (unlisten) unlisten();
  };
}
