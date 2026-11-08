# Evidence RAG — Visual Design System

## 1. Typography & Vietnamese Diacritics Integrity
- **Primary UI & Reading Font (`--font-body`, `--font-reading`)**: `"Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif`
  - Chosen specifically to guarantee 100% precomposed Vietnamese glyph coverage (`ấ, ầ, ẩ, ẫ, ậ, ố, ồ, ổ, ỗ, ộ, ớ, ờ, ở, ỡ, ợ, ứ, ừ, ử, ữ, ự, đ`) on Windows regardless of the OS ANSI/OEM codepage, preventing CJK fallback glyph splitting.
- **Monospace (`--font-mono`)**: `"Cascadia Mono", "Consolas", monospace` for SHA-256 hashes, document codes, and trace IDs.

## 2. Color Tokens
- **Brand Navy (`--color-brand-navy`)**: `#163a5f`
- **Primary Action (`--color-action`)**: `#2563eb` (hover `#1d4ed8`)
- **Background & Surface**: `#f8fafc` canvas, `#ffffff` cards/panes, `#f1f5f9` muted containers
- **Semantic Status**:
  - Verified / Active (`--color-success`): `#047857` on `#ecfdf5`
  - Unverified / Caution (`--color-warning`): `#92400e` on `#fffbeb`
  - Error / Rejected (`--color-danger`): `#b91c1c` on `#fef2f2`

## 3. Desktop Multi-Viewport Layout Architecture
- **Topbar**: Fixed `64px` height, flexbox with wrapping protection, surface switcher, mode pill, and session controls.
- **3-Pane Workspace (`>= 1024px`)**:
  - Locked to `height: calc(100vh - 64px)` so all three panes scroll independently and the Chat Composer is permanently visible at the bottom-left.
  - Synchronized `72px` header height across all three panes (`.pane-header` and `.viewer-toolbar`) so horizontal dividers align across the entire screen width.
- **Floating Chat Agent Dock (`ChatAgentDock`)**:
  - Fixed at bottom-right (`right: 24px; bottom: 24px; z-index: 850`), providing 1-click access to the Chat Agent drawer from any screen (User Workspace or Admin Portal) and native Tauri Orb collapse when running in Desktop mode.
