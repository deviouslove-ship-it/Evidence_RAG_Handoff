**Language / Ngôn ngữ:** [Tiếng Việt](README.md) · English

English counterpart of `src-tauri/README.md`. The Vietnamese file is the original.

# Evidence RAG — Windows Desktop Shell (Tauri 2)

Native shell for the USER on Windows, following section C.12 and D.5 S14 of the handoff dossier.

## Window and behavior

- `main`: an opaque window (`transparent: false`, `decorations: true`, `minWidth: 360`, `minHeight: 520`), used for login, the lookup chat frame, the source PDF viewer, and the workspace.
- `orb`: a round floating window (`url: index.html#/orb`, `72x72` logical px, `transparent: true`, `decorations: false`, `shadow: false`, `alwaysOnTop: true`, `skipTaskbar: true`). It is shown only after login (`session_started`), anchored to the right edge of the work area (`work area`) of the current monitor, and always clamped (`clamp`) inside the screen.
- Closing the `main` window during a session collapses it to the Orb / system tray instead of exiting abruptly.

## IPC commands (`window.__TAURI__.core.invoke`)

- `session_started`: turns the session state on, positions the `orb` window, and shows it.
- `session_ended`: turns the session state off, hides `orb`, and shows the `main` window again.
- `toggle_panel`: opens or collapses the `main` window beside `orb`, within the `work area`.
- `drag_orb_window({ dx, dy })`: moves the `orb` window immediately by the mouse delta `(dx, dy)`, clamped safely inside the current screen.
- `orb_drag_finished`: clamps the `orb` position onto the nearest screen and saves the coordinates to `shell-state.json`.
- `open_evidence_in_workspace({ response, selected, question, accessToken })`: shows the `main` window and brings it to the front, and emits the event `evidence-orb-sync-workspace` to load the question, the evidence (căn cứ) list, and the working session into the main lookup workspace.
- `set_always_on_top({ alwaysOnTop })`: turns the always-on-top pin on or off for the `main` window.
- `quit_app`: exits the application completely.

## Events

- `evidence-logout-requested` (and `CustomEvent('evidence:logout')`): emitted from the system-tray menu **Đăng xuất** (Log out) to the `main` window, to delete the token and end the session.
- `evidence-orb-sync-workspace`: emitted from `open_evidence_in_workspace` to the `main` window, to sync the lookup context from the Orb.

## Separating the web UI from the native shell

- The **round floating Orb** icon and window (`#/orb`) activate only when running in the Windows Native Desktop Tauri 2 environment (detected via `window.__TAURI__`).
- In an ordinary web browser, the Orb icon and the desktop toolbar are hidden automatically, so the interface stays compact, without leftover elements or position conflicts.
