# Evidence RAG — Sitemap & Screen Hierarchy

## Screens
1. **User Evidence Workspace (`surface = "user"`)**
   - Left Pane: Conversation history, quick suggestion chips, scope & effective date selector, pinned composer.
   - Center Pane: Authorized evidence cards with exact quotes, effective status badges, and 1-click PDF page open.
   - Right Pane: Hash-verified PDF iframe viewer (`#page=N`) and verbatim quote verification card.
2. **Admin Portal (`surface = "admin"`)**
   - Tab 1 (`documents`): CURATOR PDF draft upload & REVIEWER approval/rejection queue.
   - Tab 2 (`categories`): Document category management & remote AI egress policy.
   - Tab 3 (`users`): User accounts, RBAC roles, and ABAC category permissions.
   - Tab 4 (`ai_audit`): AI Model Registry, stage routing, and hash-chained audit log verification.
3. **Login & Mandatory Password Change Modal (`LoginPanel`)**
   - Centered modal overlay (`position: fixed; inset: 0`).
4. **Floating Chat Agent Widget (`ChatAgentDock`) & Native Desktop Orb (`DesktopOrb`)**
   - Bottom-right persistent Chat Agent launcher button + expandable quick-query drawer.
   - Native Tauri `#/orb` 72x72 circular floating window.
