**Language / Ngôn ngữ:** [Tiếng Việt](P2_Thiet_ke_UX_UI_D.md) · English

English counterpart of `parts/P2_Thiet_ke_UX_UI_D.md`. The Vietnamese file is the original. These parts are extracts of `docs/HOSO_BAN_GIAO.md`.

---

## D. Detailed UX/UI design

The design direction is locked: **Modern Enterprise / Evidence-First**, Light Theme by default, Navy + Blue + White + Slate. This is the application's palette. Do not take the ChatGPT palette, the DIL demo, or a framework's colors as the standard. Dark Mode is P1.

### D.1 UX principles

1. **Evidence (căn cứ) first, the explanation after.** The first thing the user sees is the verbatim source and the PDF page. The explanation is the second layer.
2. **Say clearly what is known and what is not yet known.** Every result has a scope (category, application date, data-repository date), a status label, and a coverage checklist. Do not use a self-scored percentage. Do not use decorative color to create trust.
3. **Color is not the only signal.** Every status has an icon, a text label, and a description by application date.
4. **The user keeps the right to edit.** A fact the AI inferred can always be edited. A follow-up question shows "Đang hiểu là…" (Understood as…) so it can be corrected. There is no hidden action.
5. **Do not lose context.** Opening a PDF, opening an amending administrative document (văn bản; sửa đổi), and opening the full page all keep the conversation and the results.
6. **Quiet, and readable.** The one point of emphasis is the verbatim evidence card. Everything around it is neutral. No background effect, no gradient, and no heavy drop shadow. Motion only responds to a user action.
7. **The widget and the full page share one interface language.** Shared components, a shared SSE contract, and shared labels.
8. **Interface copy is in plain Vietnamese, in the active voice, with sentence case at the start of a sentence.** A button names the action ("Tra cứu" (Search), "Lưu nháp" (Save draft), "Duyệt" (Approve)). The same action keeps the same name throughout.

### D.2 Design system

**D.2.1 Color — official tokens (SRS §9.5)**

| CSS token | HEX | Use |
|---|---|---|
| `--color-brand-navy` | `#163A5F` | Sidebar, top bar, administration-area titles, Chat Agent panel header, launcher |
| `--color-brand-navy-hover` | `#102B47` | Hover on the Navy bar, launcher hover |
| `--color-action` | `#2563EB` | Primary search button, citation link `[1]`, active tab, focus ring |
| `--color-action-hover` | `#1D4ED8` | CTA hover |
| `--color-background` | `#F8FAFC` | Background of the whole app |
| `--color-surface` | `#FFFFFF` | Chat, Evidence Cards, PDF Viewer, modal |
| `--color-surface-muted` | `#F1F5F9` | Secondary information cards, skeleton, user message |
| `--color-text-primary` | `#0F172A` | Primary content and citations |
| `--color-text-secondary` | `#475569` | Meaningful metadata, breadcrumb |
| `--color-border` | `#CBD5E1` | Input, card, and separator borders |
| `--color-evidence-bg` | `#EFF6FF` | Evidence that is selected or currently shown in the viewer |
| `--color-evidence-text` | `#1E40AF` | Citation and evidence labels |
| `--color-success` | `#047857` | A check that passed, a source that is allowed to be used; always with an icon and text |
| `--color-warning` | `#92400E` | A condition that is not certain, effectivity (hiệu lực) that is not complete |
| `--color-warning-bg` | `#FFFBEB` | Sticky Amendment Banner and temporal warning |
| `--color-danger` | `#B91C1C` | Error, repeal (bãi bỏ), a right that is blocked, an invalid citation |
| `--color-danger-bg` | `#FEF2F2` | A serious warning region |

**Additional tokens (proposed; they must pass a contrast test; if they do not pass, adjust the token):**

| Token | Suggested value | Used for |
|---|---|---|
| `--color-success-bg` | `#ECFDF5` | Background of the label "Đã xác định căn cứ" (Evidence identified) |
| `--color-highlight-fill` | `rgba(37, 99, 235, 0.22)` | Paint the cited span on the PDF (only the exact span region, `mix-blend-mode: multiply`) |
| `--color-highlight-stroke` | `#2563EB` | A 2px border around the span that is selected |
| `--color-dirty-bg` / `--color-dirty-border` | `#FFF7ED` / `#C2410C` | A chip that has been edited, and the bar "Đã chỉnh sửa dữ kiện" (Facts have been edited) (neutral / light orange) |
| `--color-overlay` | `rgba(15, 23, 42, 0.45)` | Modal background |
| `--color-focus-ring` | `var(--color-action)` | A 3px focus ring, offset 2px |

**Rules for using color**

1. The top bar and the sidebar are Navy. The reading region and the Evidence Card have a white background. The whole page is a very light gray. Blue is only for interaction (a citation link, the button "Tra cứu" (Search), focus). Blue is not used to declare that evidence is legally correct.
2. The dirty state uses neutral or light orange. A `stale` result has a text label. The skeleton is neutral. Success green is not used before the claim has been checked.
3. The PDF background is white, or it follows the original render. Do not paint color over PDF content. The highlight sits only on the span that was cited.
4. Every color goes through CSS variables in **one theme module**. Hardcoded HEX inside a component is forbidden (a lint rule). Every color pair and status has an automatic contrast test (WCAG 2.2 AA: 4.5:1 for ordinary text, 3:1 for large text and interface components).

**D.2.2 Type**

The preferred font family is `Inter, system-ui, Arial, sans-serif`, with a fallback that supports Vietnamese diacritics. Local Mode does not download an external font: bundle Inter locally only after the license is checked; otherwise use the system font.

| Role | Size / line-height | Weight | Note |
|---|---|---|---|
| Page title (h1) | 24 / 32 | 600 | One per screen |
| Area title (h2) | 20 / 28 | 600 | |
| Card title (h3) | 18 / 28 | 600 | |
| Interface content | 14 / 20 | 400, labels 500 | Buttons, tables, chips |
| Reading content | 15 / 24 | 400 | The answer, the explanation |
| Verbatim citation and long administrative-document (văn bản) text | 16 / 26 | 400 | Minimum line-height 1.5; a line is not longer than about 80 characters when the layout allows |
| Meaningful metadata | 13 / 18 | 400, `--color-text-secondary` | Symbol number, date, breadcrumb; not below 13px |

**D.2.3 Spacing, corner radius, elevation, and layers**

- Spacing steps by 4px: 4, 8, 12, 16, 24, 32, 48. Padding inside a card is 16. Between blocks inside an answer, 12–16. Between regions, 24.
- Corner radius: 6px (input, button), 8px (evidence card, table), 12px (Chat Agent panel, drawer, modal), fully round (chip, launcher, badge). Do not use one radius for everything.
- Elevation: a card uses a 1px border `--color-border`, with no drop shadow. Only a floating panel (`0 8px 24px rgba(15,23,42,0.16)`) and a modal (`0 16px 40px rgba(15,23,42,0.24)`) have a shadow.
- Layers (z-index): content 0 · sticky header 10 · viewer drawer 30 · launcher and Chat Agent panel 40 · confirmation modal 50 · toast 60. The confirmation modal is always above the Chat Agent.

**D.2.4 Icons and motion**

- An icon set packaged locally (the proposal is `lucide`, ISC license; record it in the manifest). Do not use icons from a CDN.
- Motion only responds to an action: open and close the panel (160–200ms, a slide plus a light fade), open an accordion, confirm. There is no animation that runs by itself except the skeleton and the "đang xử lý" (processing) indicator. Respect `prefers-reduced-motion` (turn off the slide, and use an instant show or hide).

### D.3 Information architecture and navigation

| Area | Role | Navigation items |
|---|---|---|
| User Portal | USER, or the right `rag.query` granted explicitly, plus a document scope | Orb home · Question answering / workspace · Lịch sử của tôi (My history) · Bộ nhớ của tôi (My memory) · Theo dõi (Watch) (P1) |
| Document repository | CURATOR, REVIEWER | Tài liệu (Documents) · Hàng đợi duyệt (Review queue) · Quan hệ sửa đổi (Amendment relations) · Đề xuất của AI (AI suggestions) |
| Administration | SYS_ADMIN | Danh mục (Categories) · Người dùng và quyền (Users and rights) · Domain cho phép (Allowed domains) · Mô hình AI và chế độ (AI models and mode) · Cấu hình bộ nhớ (Memory configuration) |
| Quality | CURATOR, REVIEWER, SYS_ADMIN | Bộ kiểm thử (Test suite) (Gold, trap set) · Chạy benchmark (Run benchmark) · Dashboard |
| Audit | AUDITOR | Nhật ký (Log) · Bằng chứng truy cập (Access evidence) |

- **The Chat Agent (launcher at the right corner) appears on every Tra cứu (Search) page and every Kho tài liệu (Document repository) page (read mode).** It is hidden on sign-in and collapsed on the Curator Split-View.
- A navigation item the user has no right to **is not displayed** (filtered from the server, not merely hidden in the interface).
- The Search region has only a top bar (Navy). The administration region and the document repository add a left bar (Navy, collapsible).

Standard routes: `/login` is shared; `/app/*` is the User Portal; `/admin/*` is the Admin Portal, with its own layout, state, and navigation; `/` routes by rights, or by the portal choice of an account that has several rights. SYS_ADMIN is not admitted to Tra cứu (Search) by default. Switching portals does not raise rights, and it does not move a private conversation onto an administration screen. The desktop opens the User Portal inside the shell. An administration route opens only when the right exists and the action is explicit.

### D.4 Shared layout and size response

| Breakpoint | Layout |
|---|---|
| ≥ 1280px | Question answering: two regions — a left column "Hỏi và căn cứ" (Question and evidence) (about 5/12) and the PDF Viewer (about 7/12); the split can be dragged. Split-View: two equal halves |
| 768–1279px | One column for the question and the evidence. The PDF Viewer opens as a right drawer about 70% of the screen width |
| < 768px | One column. The PDF Viewer and the Chat Agent open full screen with a back button. The primary action sits in an easy-to-tap region (≥ 44×44px) |

The panel and the viewer sit side by side only when the available region is at least `panel_width + viewer_min_width + gap + safe_areas`. `viewer_min_width=480px` and a gap of 16px are the initial configuration tokens. Do not apply “viewer 60% + panel 380px” unconditionally on a tablet. When space is short: the viewer replaces the panel's content region, or it opens full-frame with “Quay lại hội thoại” (Back to the conversation). Keep the session and the scroll position. Do not stack two interactive regions. The actual width and the zoom decide the layout change, not the breakpoint name alone.

The top bar of the Question answering page: logo / system name · **Danh mục ▼** (Category ▼) · **Loại tài liệu ▼** (Document type ▼) · **Ngày áp dụng** (Application date) (default "Hôm nay" (Today), together with the specific date) · a read-only mode badge (**API Mode** or **Local Mode · offline**) · the user menu. When `as_of_date` is not today, the date field switches to an emphasized style (a light orange border plus the label "Tra cứu theo ngày quá khứ" (Search by a past date)).

### D.5 Detailed screens

#### S1. Question answering (full page)

Purpose: ask, see the evidence first, read the analysis, and open the source.

```text
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ Evidence RAG  [Danh mục ▼] [Loại tài liệu ▼] [Ngày áp dụng: 21/10/2026 ▼] [Local Mode]  │ Navy
├───────────────────────────────────────────────┬─────────────────────────────────────────┤
│ [Trả lời] [Phân tích] [Liên quan]              │ PDF VIEWER (S2)                          │
│                                               │ Số hiệu · Cơ quan · Version · Hash       │
│ Phạm vi: Danh mục X · Ngày áp dụng 21/10/2026 │ Chương > Điều 5 > Khoản 2                │
│ · Kho dữ liệu cập nhật 20/10/2026             │ ┌──────────────────────────────────────┐ │
│                                               │ │ ⚠ Khoản này đã được sửa đổi bởi …    │ │ sticky
│ ┌ Mô tả tình huống hoặc hỏi về Điều, Khoản… ┐ │ │   từ ngày … — Xem văn bản sửa đổi    │ │
│ └───────────────────────────────  [Tra cứu] ┘ │ └──────────────────────────────────────┘ │
│                                               │   …nội dung PDF…                         │
│ Dữ kiện: [Đối tượng ✎] [Thời điểm ✎]          │   [ĐOẠN ĐƯỢC TÔ SÁNG]                   │
│          [Hồ sơ ✎ chưa xác nhận]              │                                          │
│ ▸ Đã chỉnh sửa dữ kiện — kết quả bên dưới dựa │ ‹ Trang 12/48 ›  Tìm trong văn bản       │
│   trên dữ kiện trước đó [Cập nhật dữ kiện &   │ Bản hiện hành │ Bản tại ngày …           │
│   Tra cứu lại]                                │ Liên kết trang công bố chính thức        │
│                                               │                                          │
│ ● Có điều kiện — cần xác minh thêm hiệu lực   │                                          │
│ CĂN CỨ  [Quy định chính][Điều kiện][Ngoại lệ] │                                          │
│  [1] Điều 5 khoản 2 · số hiệu … · bản 3        │                                          │
│      “…nguyên văn 2–3 dòng…”  [Mở trong PDF]  │                                          │
│  [2] …                                        │                                          │
│ PHÂN TÍCH CÓ DẪN CHỨNG                         │                                          │
│  • Nhận định … [1][2]                          │                                          │
│ THÔNG TIN CÒN THIẾU  [Ngày xảy ra sự việc] …   │                                          │
│ ĐÃ KIỂM TRA  ✔ Nguồn  ✔ Trích dẫn  ⚠ Hiệu lực │                                          │
│ CÂU HỎI TIẾP THEO  (chip) (chip)               │                                          │
│ Sao chép kèm phạm vi · Phản hồi                │                                          │
│ Kết quả hỗ trợ tra cứu và tham mưu, không …    │                                          │
└───────────────────────────────────────────────┴─────────────────────────────────────────┘
```

Order of blocks in the **Trả lời** (Answer) tab: scope → question field → facts → the "đã chỉnh sửa" (edited) bar (if present) → status label → evidence grouped by role → finding with citations → information still missing → coverage checklist → next questions → actions and the notice.

The **Phân tích** (Analysis) tab (A1, A3, A4, A5): a table "Điều kiện áp dụng" (Conditions of application) (already met / not yet verified / exception / time marker / consequence stated in the administrative document, each row with `[n]`), a list of points to notice, and a version comparison of the Article (Điều) currently being viewed. The **Liên quan** (Related) tab (A6, A10): guiding administrative documents, amending administrative documents (sửa đổi), references to and from the node currently being viewed, and the amendment chain.

Statuses:

| Status | What is shown |
|---|---|
| Empty | The question field and 3 examples of how to ask (chips): "Hỏi theo Điều/Khoản" (Ask by Article/Clause), "Mô tả một tình huống" (Describe a situation), "So sánh với quy định cũ" (Compare with the old provision). No fake data |
| No category selected | The question field is locked. The note "Chọn danh mục để bắt đầu" (Choose a category to begin). The category chip is emphasized |
| Phase 1 running | A neutral skeleton (`--color-surface-muted`) plus "Đang tìm căn cứ trong danh mục đã chọn…" (Searching for evidence in the selected category…) |
| Phase 1 done | Evidence cards appear. The line "Đã tìm thấy và kiểm tra nguồn của X căn cứ. Đang phân tích điều kiện áp dụng, hiệu lực, quy định chuyển tiếp và ngoại lệ…" (Found and checked the source of X pieces of evidence. Analyzing conditions of application, effectivity, transitional provisions, and exceptions…) |
| Phase 2 done | Claims, the status label, and the full checklist |
| Insufficient evidence | The label "Thiếu căn cứ" (Insufficient evidence) plus an explanation plus a suggestion to ask again plus (if any) the nearest evidence that was checked, stating clearly "chưa trả lời được câu hỏi" (the question cannot be answered yet) |
| False premise (L0) | "Không có [Điều X] trong [văn bản]. Văn bản này có Điều 1 đến Điều N." (There is no [Article X] in [the administrative document]. This administrative document has Article 1 through Article N.) |
| Explanation generation failed | Keep the valid evidence plus "Giải thích tạm thời không khả dụng. Các căn cứ bên dưới đã được kiểm tra nguồn." (Explanation temporarily unavailable. The evidence below has had its source checked.) |
| Effectivity snapshot stale | A warning bar: "Dữ liệu hiệu lực đang được cập nhật. Chưa thể khẳng định hiệu lực tại ngày này." (Effectivity data is being updated. Effectivity on this date cannot be asserted yet.) |
| Old result (`stale`) | The label "Kết quả dựa trên dữ kiện trước đó" (Result based on the previous facts) until a new result exists |
| Network or server error | A message that states what failed, and a button "Thử lại" (Retry). Do not clear what the user has entered |

#### S2. PDF Viewer

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ ‹ Quay lại   Tên văn bản · Số hiệu · Cơ quan · Bản 3 ▼ · Hash 9f3a…   ⤓ ↗  │ toolbar
│ [Đang áp dụng ✔ tại 21/10/2026]  (nhãn hiệu lực của node đang xem)         │
├────────────────────────────────────────────────────────────────────────────┤
│ ⚠ Khoản này trên PDF gốc đã được sửa đổi bởi [văn bản] từ ngày [ngày]      │ sticky
│   [Xem văn bản sửa đổi] [Xem nội dung áp dụng tại ngày tra cứu]  ▾ thu gọn │
├────────────────┬───────────────────────────────────────────────────────────┤
│ MỤC LỤC        │                                                           │
│ ▸ Chương I     │   …trang PDF gốc…                                         │
│ ▾ Chương II    │   ┌─ Điều 5 ─ …                                          │
│   ▾ Điều 5     │   │ 2. [đoạn được tô sáng] ◂ huy hiệu "Đã sửa đổi"         │
│     Khoản 1    │   └────────────────────────────────────────────────────── │
│   ● Khoản 2    │                                                           │
├────────────────┴───────────────────────────────────────────────────────────┤
│ ‹ Trang 12 / 48 ›   Tìm trong văn bản [          ]   Bản hiện hành │ Bản tại ngày … │
└────────────────────────────────────────────────────────────────────────────┘
```

- The toolbar always shows the effectivity label of the node currently being viewed (collapsing the banner does not remove this label).
- The table of contents is built from the database (`document_nodes`). A click jumps to the PDF. The node currently being viewed has a ● mark and `aria-current`.
- Highlight: background `--color-highlight-fill`, border `--color-highlight-stroke`. Only the span region that was cited. Scroll automatically to the span.
- **Fallback when the bounding box is not reliable:** open the correct page, show a pane "Đoạn trích để đối chiếu" (Excerpt for comparison) beside it, with the line "Chưa tô sáng chính xác vị trí đoạn này trên trang." (The position of this passage on the page has not been highlighted precisely.)
- The copy as of a date: choose the version. The old PDF is still viewed in full, with the banner.
- The PDF download button appears only when the right exists. The link "Trang công bố chính thức" (Official publication page) appears only when the curator has verified it.
- On a phone: full screen. The table of contents becomes a drawer. The toolbar collapses to a title plus a menu.

#### S3. Chat Agent (widget at the right corner)

**Launcher.** A round button of 56px, background `--color-brand-navy`, a white conversation icon. 24px from the right edge and the bottom edge (16px on a phone), plus the safe area. Hover `--color-brand-navy-hover`. Focus: a 3px ring `--color-focus-ring`, 2px away. Tooltip "Hỏi về văn bản" (Ask about an administrative document). `aria-label="Mở trợ lý tra cứu"` (Open the search assistant). A round 12px badge with a white border: action blue means there is a new response; orange (`--color-warning`) means there is a result that needs to be checked again. It does not turn itself on, and it does not open itself.

**Panel (web / desktop frame).** Desired width 420px (≥1280) or 380px (768–1279), always clamped inside the work area and the safe area. Maximum height `min(720px, 100vh − 96px)`, corner radius 12px. The Orb remains the toggle control, with a label that matches the state. Another click collapses the panel. The native shell follows S14. Do not add an extra square or a background window around the Orb.

```text
                                   ┌──────────────────────────────────────┐
                                   │ Trợ lý tra cứu        ⤢  ▁  ✕        │ Navy
                                   ├──────────────────────────────────────┤
                                   │ [Danh mục X ▼] [21/10/2026 ▼] [Local]│ thanh phạm vi
                                   │ Đang hiểu là: “…câu đã viết lại…” ✎  │ (khi hỏi nối tiếp)
                                   │ [Trả lời] [Phân tích] [Liên quan]    │
                                   ├──────────────────────────────────────┤
                                   │                    ┌───────────────┐ │
                                   │                    │ câu hỏi của tôi│ │
                                   │                    └───────────────┘ │
                                   │ ● Có điều kiện                       │
                                   │ ┌ [1] Điều 5 khoản 2 · số hiệu … ──┐ │
                                   │ │ “…nguyên văn…”      [Mở trong PDF]│ │
                                   │ └───────────────────────────────────┘ │
                                   │ Nhận định có dẫn chứng … [1]         │
                                   │ Còn thiếu: (Ngày xảy ra sự việc)     │
                                   │ Hỏi tiếp: (…) (…)                    │
                                   │ Sao chép kèm phạm vi · Phản hồi      │
                                   ├──────────────────────────────────────┤
                                   │ ┌ Mô tả tình huống hoặc hỏi Điều… ┐  │
                                   │ └────────────────────── [Tra cứu] ┘  │
                                   │ Hỗ trợ tra cứu, không thay quyết định │
                                   └──────────────────────────────────────┘
                                                                     (◉) launcher
```

Buttons in the header: **⤢ Mở trang đầy đủ** (Open the full page) (keeps the session) · **▁ Thu nhỏ** (Minimize) (back to the launcher, keeping state) · **✕ Đóng** (Close).

**Behavior**

- Open from the launcher or from a configurable shortcut (by default no global shortcut is assigned, to avoid conflicts; the owner may turn one on). `Esc` closes the panel when focus is inside it. Focus returns to the launcher.
- Session state is kept on the server. Moving between pages inside the application does not lose the conversation.
- Press `[n]` or "Mở trong PDF" (Open in PDF): if there is enough room under D.4, the viewer sits beside the panel; if room is short on a tablet or a narrow window, switch to a single frame with “Quay lại hội thoại” (Back to the conversation). Do not cover a citation or the composer with another panel. On native, prefer the workspace in the same session when a wide PDF needs to be read.
- The user's message: aligned right, background `--color-surface-muted`. The assistant's answer: a white block with a border. **Do not use a chat bubble.** The blocks inside follow the same order as S1, but the evidence card is compact (symbol number, Article (Điều)/Clause (Khoản)/Point (Điểm), 2 excerpt lines, and an open button).
- A follow-up question: show the bar "Đang hiểu là: …" (Understood as: …) (with an edit button). If a key condition is missing, ask **one** question again using choice chips.
- An old result after the snapshot changes: the label "Cần kiểm lại" (Needs recheck) with the button "Tra cứu lại với dữ liệu mới" (Search again with the new data). The launcher has an orange badge.
- There is no button that approves or executes business work.
- The not-stored mode: a lock icon in the header and the line "Hội thoại này sẽ không được ghi nhớ." (This conversation will not be remembered.)
- There is a “Dừng” (Stop) button while a run is in progress. Stop applies only to the question-and-answer turn. It does not affect an administration task. “Thử lại” (Retry) after an error is a new run on purpose. Show the old result as the previous turn, and do not duplicate the question.

**Phone:** the panel is full screen (a bottom sheet at 100% height), with a sticky header and a composer stuck to the bottom according to `visualViewport`, so the keyboard does not cover it.

**Special statuses**

| Status | What is shown |
|---|---|
| First time | A short greeting plus 3 example chips of how to ask. No long introduction |
| No category selected | The scope bar is emphasized. The composer is locked, with the reason |
| Connection lost | "Mất kết nối tới máy chủ. Nội dung bạn nhập vẫn được giữ." (Connection to the server was lost. What you entered is still kept.) plus Thử lại (Retry) |
| Local Mode, local model failed | Evidence that has been checked is still shown. "Giải thích tạm thời không khả dụng" (Explanation temporarily unavailable). **Do not** switch to the API |
| No right | "Chưa tìm thấy tài liệu được phép truy cập." (No document you are allowed to access was found.) (do not reveal that a document exists) |

#### S4. Document list and document record (CURATOR/REVIEWER)

```text
┌ Tài liệu ──────────────────────────────────────────────────────────────────┐
│ [Tìm theo số hiệu, tiêu đề]  [Danh mục ▼] [Loại ▼] [Trạng thái ▼]          │
│                                   [Tải PDF lên]  [Nhập từ URL]              │
├────────────────────────────────────────────────────────────────────────────┤
│ Tiêu đề / số hiệu │ Loại │ Cơ quan │ Danh mục │ Phiên bản │ Trạng thái │ ⋯ │
│ …                                                                          │
└────────────────────────────────────────────────────────────────────────────┘
```

- The **Trạng thái tài liệu** (Document status) column: Nháp (Draft) · Chờ duyệt (Waiting for review) · Đã duyệt (Approved) · Tạm đình chỉ (Temporarily suspended) · Đã thay thế (Replaced) · Hết hiệu lực (No longer in effect) · Chưa rõ (Unknown) (icon + text). The **Hiệu lực node** (Node effectivity) column summarizes: "Có N node chưa xác minh" (There are N nodes not yet verified).
- **Tải PDF lên (Upload PDF):** supports selecting many PDFs at once (`multiple`); allows independent metadata to be declared for each administrative document (title, symbol number, official source URL, issue date); sends each file sequentially to `POST /api/v1/admin/documents/upload` so the PDF processor is not overloaded; shows progress `Đang nhập tệp n/tổng…` (Importing file n of total…), a separate status for each file (`ready`, `uploading`, `success`, `failed`, `unknown`), a button "Dừng nhập tệp" (Stop importing files) (`AbortController`), and a button "Thử lại các tệp chưa thành công" (Retry the files that did not succeed); a two-layer duplicate check (block a byte-identical SHA-256 duplicate with status 409 `DUPLICATE_PDF_HASH`; warn on duplicated NFC text content with `possible_duplicate_content`, together with a list of at most 5 draft or source copies for comparison).
- **Nhập từ URL (Import from URL):** an input field. If the domain is not on the list: "Tên miền này chưa nằm trong danh sách cho phép. Nhờ quản trị viên thêm tên miền sau khi xác minh." (This domain is not yet on the allowlist. Ask an administrator to add the domain after verification.) There is no skip button.
- The document-record page has tabs: **Thông tin** (Information) (standard metadata, source, hash, and the button "Mở trang công bố chính thức" (Open the official publication page) if it has been verified) · **Phiên bản** (Versions) · **Cây điều khoản** (Article tree) · **Quan hệ** (Relations) (amendment/reference) · **Lịch sử** (History) (audit).
- The list shows only documents the user has a right to (filtered on the server).

#### S5. Review queue (risk-prioritized)

Table: **Tài liệu và phiên bản** (Document and version) · **Lý do vào hàng đợi** (Reason for entering the queue) · **Rủi ro** (Risk) · **Người phụ trách** (Person responsible) · **Hạn** (Due) · **Trạng thái** (Status).

- Reasons: Độ tin cậy parse thấp (Low parse confidence) · Nhảy khoản (Skipped clause) · Chuyển mã font (Font encoding conversion) · Tọa độ trang lệch (Page coordinates misaligned) · Hiệu lực chưa duyệt (Effectivity not yet approved) · Đề xuất của AI (AI suggestion).
- Risk: **Cao (High) / Trung bình (Medium) / Thấp (Low)**, shown with an icon and text (not color alone). The default sort puts High first.
- Filter by reason, risk, and person responsible. A bulk action is allowed only for **gán người phụ trách** (assigning the person responsible). Approval is always per item.
- An empty queue: "Không có mục chờ duyệt. Tài liệu mới nạp sẽ xuất hiện ở đây." (Nothing is waiting for review. A newly ingested document will appear here.)

#### S6. Curator Split-View

```text
┌ Tài liệu X · bản 3 · Mục 4/17 trong hàng đợi │ Đã lưu nháp 14:32 │ Revision 8 ─────────┐
├───────────────────────────────────────┬───────────────────────────────────────────────┤
│ PDF.js — bản bất biến                 │ [Cây node] [Hiệu lực] [Quan hệ] [Đề xuất của AI]│
│ [Trang 12 ▼]  tô sáng span đang chọn  │ ▾ Chương II                                   │
│                                       │   ▾ Điều 5                                     │
│   …trang PDF…                         │     ● Khoản 2  (độ tin cậy parse: thấp)        │
│   [span]                              │ ─ Form node ──────────────────────────────────│
│                                       │ Nhãn [Khoản 2]  Vị trí [5.2]                   │
│                                       │ Hiệu lực từ [..] đến [..]  Trạng thái [Chưa rõ]│
│                                       │ Quan hệ sửa đổi [+ Thêm]                       │
│                                       │              [Bỏ qua]  [Lưu nháp]  [Duyệt]     │
└───────────────────────────────────────┴───────────────────────────────────────────────┘
```

- Click a node → the PDF jumps to the span. Click in the PDF → focus the corresponding node. A clause that does not yet have a node → open the task "Phân tích lại trang" (Analyze the page again).
- **Automatic draft save** (the only notice is "Đã lưu nháp" (Draft saved)) is different from **Duyệt** (Approve). Approve uses a separate endpoint, the REVIEWER role, and checks `If-Match` and the revision. On a revision conflict, show "Mục này vừa được người khác sửa. Tải lại để xem thay đổi." (Someone else just edited this item. Reload to see the change.)
- Shortcuts (next/previous node) **are disabled while text is being entered**. There is no approve shortcut.
- Approving a change of effectivity or of an amendment relation: a confirmation dialog: "Thay đổi này ảnh hưởng cách hệ thống trả lời với các ngày từ [ngày]. Hành động được ghi nhật ký." (This change affects how the system answers for dates from [date]. The action is written to the log.) — buttons "Duyệt" (Approve) / "Quay lại" (Go back).
- The **Đề xuất của AI** (AI suggestions) tab (C1): each suggestion has a type, a source span, a confidence level as a label, and the buttons **Chấp nhận vào nháp (Accept into the draft) / Sửa (Edit) / Từ chối (Reject)**. A CURATOR accept only saves a draft and an audit record. Approval of the document, of effectivity, or of an amendment goes through the REVIEWER and a separate endpoint. It does not publish quietly. A bulk operation needs confirmation.
- The Chat Agent is minimized on this screen (it does not cover the form).

#### S7. Categories (SYS_ADMIN/CURATOR)

A drag-and-drop category tree, with a configurable depth. Columns: Tên (Name) · Mã cố định (Fixed code) · Người phụ trách (Person responsible) · Quyền xem (View right) · Số tài liệu (Document count) · Trạng thái (Status) (Hoạt động (Active) / Ẩn (Hidden) / Đã xóa (Deleted)). Actions: Thêm (Add) · Sửa (Edit) · Ẩn (Hide) · Xóa mềm (Soft-delete) · Khôi phục (Restore) · Nhập/Xuất JSON/CSV (Import/Export JSON/CSV) (with a check step before applying). A soft delete states clearly: "Tệp gốc và embedding vẫn được giữ nếu tài liệu còn thuộc danh mục khác." (The original file and the embedding are still kept if the document still belongs to another category.) Creating a cycle is forbidden: report the error immediately in the parent-category field.

#### S8. Allowed domains (SYS_ADMIN)

Table: **Tên miền** (Domain) · **Người xác minh** (Person who verified) · **Ngày xác minh** (Verification date) · **Ghi chú** (Note) · **Trạng thái (Bật/Tắt)** (Status (On/Off)) · **Lần dùng gần nhất** (Most recent use). The button **Thêm tên miền** (Add a domain) opens a 3-step wizard: (1) enter the domain name → the system checks DNS, HTTPS, and that it is not an internal address; (2) confirm the person who verified it and the source note; (3) turn it on. Every change is audited. Turning a domain off: the warning "Các lần nhập mới từ tên miền này sẽ bị chặn." (New imports from this domain will be blocked.)

#### S9. AI models and operating mode (SYS_ADMIN)

- **Mode:** two cards, **API Mode** and **Local Mode**, showing the current status and the conditions required (for Local Mode: the `verify-egress` result, and that a local model is ready). Changing the mode needs confirmation and an audit record.
- **Model Registry:** a table of Provider · Endpoint · Model · Capability (chips: Phân tích/Chat (Analysis/Chat) · Embedding · Rerank · Sinh (Generation) · OCR) · Privacy zone · Status · Cost/quota · [Kiểm tra kết nối] (Check connection). An API key is entered only once, shown masked, and cannot be read back.
- **Stage routes:** a matrix of Stage × (API Mode, Local Mode) that chooses the model. Fallback stays inside the same privacy zone. Warn if a Local Mode stage points at a model that does not run locally.
- The API configuration form includes the supported adapter/provider, the endpoint, the model ID, parameters, and a secret entered once. The Local form includes the approved internal runtime or endpoint, the artifact or model ID, the revision, and parameters. Statuses are “Chưa cấu hình” (Not configured), “Chưa kiểm tra” (Not checked), “Sẵn sàng” (Ready), and “Lỗi” (Error). Do not prefill a mandatory model, key, or host. A connection check uses only synthetic data and still follows the egress policy.
- A local runtime or model is chosen by a manifest ID or by a relative path inside the install root that has been checked. The server resolves it and checks containment under B.8. An API or LAN endpoint is still an endpoint configuration that has a policy. The form must not become a way to read or run an arbitrary file outside the root.
- **Policy by category:** the switch "Cho phép xử lý bằng AI từ xa" (Allow processing by remote AI) defaults to **Tắt** (Off). Turning it on needs confirmation, with a warning about the data that is sent outside.
- The model's chain-of-thought is not displayed anywhere.

#### S10. My memory (USER)

The blocks: **Chế độ không lưu** (Not-stored mode) (a switch) · **Hội thoại gần đây** (Recent conversations) (a list; view the summary, delete one session) · **Sở thích** (Preferences) (opt-in: default category, frequently used scope) · **Thời hạn lưu** (Retention period) (read-only, set by administration) · **Xóa tất cả bộ nhớ** (Delete all memory). A short explanation: "Bộ nhớ giúp trợ lý hiểu câu hỏi nối tiếp. Câu trả lời luôn lấy căn cứ lại từ kho tài liệu." (Memory helps the assistant understand a follow-up question. The answer always fetches evidence again from the document repository.) Delete-all needs confirmation, and it is a real delete.

#### S11. Test suite: reviewing Gold and the trap set (REVIEWER / business specialist)

```text
┌ Bộ kiểm thử · Gold v0 · Đã duyệt 62 / 180 · Calibration 54 │ Held-out 126 (khóa) ───┐
├──────────────────────┬──────────────────────────────────────────────────────────────┤
│ Danh sách case       │ Case G-0073                                                   │
│ [lọc: Chưa duyệt ▼]  │ Câu hỏi: …                          Ngày áp dụng: …           │
│ G-0071 ✔ Đã duyệt    │ Căn cứ do agent đề xuất: số hiệu · Điều/Khoản/Điểm · bản       │
│ G-0072 • Chưa duyệt  │ “…đoạn trích…”  [Mở trong PDF]                                 │
│ G-0073 • Chưa duyệt  │ Đáp án mẫu (agent soạn): …                                    │
│ …                    │ Loại: [Trực tiếp ▼]  Có cần trả lời "không đủ căn cứ"? [ ]    │
│                      │ [Duyệt]  [Yêu cầu sửa + ghi chú]  [Loại bỏ case]              │
└──────────────────────┴──────────────────────────────────────────────────────────────┘
```

- Each case has a status **Nháp → Đã duyệt / Cần sửa / Loại bỏ** (Draft → Approved / Needs changes / Discarded), the reviewer, and the time. **Only a case that is Đã duyệt (Approved) counts toward the standard.**
- The reviewer always sees the original source passage and can open the PDF. There is no "duyệt tất cả" (approve all) button.
- The held-out set is locked in both the API and the interface against the person who tunes. The case and the answer are not in that person's benchmark log. Show `scenario_group_id`, `split_revision`, and whether the candidate is frozen. The final evaluation runs only after the configuration is frozen. A set that has been used to decide an edit or a tune is no longer called an independent held-out set.
- The trap set has its own tab and the same review method.

#### S12. Quality dashboard (SYS_ADMIN, REVIEWER)

Metric tiles and charts over time: `retrieval_ms`, `evidence_ready_ms`, `first_claim_ms`, `final_answer_ms` (P50/P95, a line over time); the rate of correct and incorrect refusal; `unsupported_claim_rate`, `wrong_doc_rate`, `wrong_node_rate`, `false_premise_detection_rate`, `validator_reject_rate`; Gold review progress (approved / the target of 150–200); benchmark-run history with a filter by model, tokenizer, and corpus hash. Every figure records **the measurement environment and the time**. Do not display a number when there is no data yet (show "Chưa có số đo" (No measurement yet)).

#### S13. Sign-in, rights, and error pages

- Local sign-in. Do not use an outside service (captcha, font, analytics). A wrong password: "Tên đăng nhập hoặc mật khẩu không đúng." (The username or password is incorrect.) A temporary lock after many failures, stating the wait time.
- No right to enter a page: "Bạn chưa có quyền vào mục này." (You do not yet have the right to enter this section.) (do not hint at what that section contains).
- 404/500: state what happened, a reference code to report to administration, and a button back to the home page.

#### S14. USER desktop shell

Reuse S3 (chat), S1 (workspace), S2 (viewer), S10 (memory), and S13 (sign-in). Do not duplicate the workflow. The state chain: `SIGNED_OUT → LOGIN → ORB ↔ PANEL ↔ WORKSPACE`. A lost session returns to LOGIN. A lost network keeps the draft and a clear error state.

- **Login:** an opaque window, text that is easy to read, not transparent. A successful sign-in closes or hides the login frame completely before the Orb appears. Do not leave a stray shadow or an extra interactive surface behind it.
- **Orb:** a circle of 56–64px, with the background and the hit-test region matching the shape. No circle inside a square, and no outer border frame or window shadow. Open and collapse by a repeated click. If drag is turned on, distinguish a drag from a click, and do not capture events outside the Orb.
- **Panel and workspace:** an opaque background following the theme. A separate drag region does not cover the assistant's name, a button, or text. The resize region is on its own edges and corners, with a minimum size and a clamp to the work area. A transparent window is not required for reading content.
- **Position:** take the work area, DPI, and monitor from the platform API. Remember the user's position and size choice if that is allowed. Do not store conversation content in local storage. After a monitor or DPI change, bring the window back into the visible region.
- **System tray:** Hiện/Ẩn trợ lý (Show/Hide the assistant), Đăng xuất (Sign out), Thoát (Exit). Equivalent controls exist inside the app for keyboard users. Closing the panel collapses to the Orb. Hide temporarily leaves only the tray. Exit ends the client. It does not stop the LAN server.
- **Installation:** the desktop shell, helper, and runtime use the dependency manifest under the configured root `E:\Programs`, following B.8. Do not hardcode PATH or the LLM in the frontend, the shell, or the helper. Take the executable and the model from configuration or the manifest. Do not depend on the global PATH, and do not install a tool quietly into the user profile.
- **Always-on-top toggle:** it is a user preference, default OFF. It does not block the sign-in window or a system modal. Do not open a console or cmd window when the app or a background helper runs.
- **Shared flow:** opening the full view, opening a PDF, or collapsing does not lose the session. The backend is the source of conversation state. Presentation state is separate from business data. Do not simulate AI when the model is not yet configured. Do not mix User and Admin.

### D.6 Component library

Every component uses the shared design tokens and has a story or a state test.

| Component | Main states and properties | Accessibility |
|---|---|---|
| `AppShell`, `TopBar`, `SideNav` | Collapsed/open; items follow rights | Landmarks `banner` / `navigation` / `main`; a skip link |
| `ScopeBar` (`CategorySelect`, `DocTypeSelect`, `AsOfDatePicker`, `ModeBadge`) | A past `as_of_date` is emphasized; the badge is read-only | A full label for each control |
| `QueryComposer` | Empty, typing, sending, locked (no category selected); Enter sends, Shift+Enter inserts a new line | `aria-describedby` for the lock reason |
| `FactChip` | `user_confirmed` (solid stroke), `extracted_unconfirmed` (dashed stroke + "chưa xác nhận" (not yet confirmed)), `inferred_uncertain` (dotted stroke + "suy đoán" (inferred)); being edited; edited (dirty) | Edit and delete buttons have labels; changes are announced through `aria-live` |
| `DirtyFactBar` | Shown when a chip is dirty; the button "Cập nhật dữ kiện & Tra cứu lại" (Update facts and search again) is enabled when valid | Role `status` |
| `ResultStatus` | 4 labels + "Chưa tìm thấy tài liệu được phép truy cập" (No document you are allowed to access was found) (D.7) | Icon + text |
| `EvidenceGroupTabs` | Tabs by role (show only a tab that has cards) | The WAI-ARIA tabs pattern |
| `EvidenceCard` | Compact (2–3 lines) / expanded; selected; the label "Nguồn ngoài danh mục" (Source outside the category); `EffectiveBadge`; `stale` | The button "Mở trong PDF" (Open in PDF) has a full name |
| `CitationLink` (`[n]`) | Hover shows a 2-line preview; opens the viewer; checks rights on open | Alternative text "Căn cứ n: [số hiệu, Điều…]" (Evidence n: [symbol number, Article…]) |
| `CoverageChecklist` | Each item: Đạt (Met) / Chưa đạt (Not met) / Chưa xác minh (Not yet verified); collapsed "Đã kiểm tra 3/4" (Checked 3 of 4) | A list with status text |
| `ClaimItem` | Has `[n]`; claim status; "chưa xác minh" (not yet verified) | The claim is tied to the evidence through `aria-describedby` |
| `MissingInfoChips`, `FollowUpChips` | Press to fill in or to ask; a configurable maximum number of chips | Real buttons, not a `div` card |
| `AnalysisTable` (A1) | Row: condition · status (already met / not yet verified / exception) · evidence `[n]` | A table with column headers |
| `NoteHighlights` (A4) | Turn emphasis on or off in the card and in the viewer | A switch with a label |
| `VersionDiff` (A5) | Side by side / interleaved; additions and removals are marked by a symbol and by text | Not color alone |
| `RelatedList` (A6) | Groups: guiding administrative document · amendment · reference to · reference from; the label "chưa duyệt" (not yet approved) | A list with levels |
| `PdfViewer`, `PdfToolbar`, `ArticleTree` | Loading, error, fallback; a collapsible table of contents | Keyboard navigation; `aria-current` |
| `AmendmentBanner` | `modified`, `repealed`, `suspended`, `not_yet_effective`, `unknown`; collapsed, but the label remains on the toolbar | Role `alert` when open; text + icon |
| `TwoPhaseSkeleton` | Phase 1, transition to Phase 2 | `aria-busy`, a phase announcement |
| `StaleLabel`, `StaleResultOverlay` | A label on the old result | `aria-live` polite |
| `FeedbackDialog` | 4 types + a note | Focus management |
| `CopyWithScope` | The copy includes the scope, the application date, and the warning | The announcement "Đã sao chép" (Copied) |
| `AgentLauncher`, `AgentPanel` | Closed, open, minimized, full screen; a badge | See D.9 |
| `DesktopShell`, `DesktopWindowControls`, `TrayMenu` | Login / Orb / Panel / Workspace, drag/resize, DPI, show/hide/sign-out/exit | A separate drag region; a keyboard menu and buttons; native does not drop focus |
| `MemoryCenter`, `SessionMemoryDrawer` | The blocks in S10 and the RAM session-memory drawer: a list of facts/items, a count badge, Stop/Retry buttons for the turn, delete one item, delete all RAM, the switch "Lưu vào sở thích tra cứu" (Save to search preferences) | The switch label is clear; role status for updates |
| `DataTable`, `ReviewQueueTable` | Sort, filter, empty, error; pagination | Column headers have `scope`; a row can be selected with the keyboard |
| `CuratorSplitView`, `NodeForm` | Draft/approve, revision conflict | Shortcuts only when focus is not in an input |
| `AiSuggestionPanel` | Accept / Edit / Reject, and the reason for rejection | Confidence is a text label |
| `ConfirmDialog` | Describes the concrete consequence; the button names the action | Modal; returns focus |
| `JobProgress` | Waiting, running, needs review, error, cancelled, done | The progress bar has text |
| `AllowlistTable`, `DomainWizard` | 3 steps, a check | |
| `ModelRegistryTable`, `ModeCard` | AI Provider/Model configuration table: adapter, endpoint (LAN/localhost supported), model ID, params (temperature, max_tokens, json_mode), secret_ref (denylist filter), in-place update | Mask the key; warn on a wrong route; connection check (probe) |
| `MetricTile`, `LatencyChart` | Has data / "Chưa có số đo" (No measurement yet) | A chart is accompanied by an alternative data table |
| `GoldReviewList`, `GoldCaseView` | Draft / Approved / Needs changes / Discarded; held-out is locked | |
| `EmptyState`, `ErrorState`, `Toast` | States the next action | `role="status"` / `alert` |

### D.7 Standard labels and statuses

**Question-answering results**

| Label | Icon | Color | When |
|---|---|---|---|
| Đã xác định căn cứ (Evidence identified) | check-circle | `--color-success` on `--color-success-bg` | The source, effectivity, and conditions of application have been checked by the rules, and coverage is sufficient |
| Có điều kiện (Conditional) | alert-triangle | `--color-warning` on `--color-warning-bg` | A condition, an exception, or effectivity is not yet verified |
| Thiếu căn cứ (Insufficient evidence) | file-search | `--color-text-secondary` on `--color-surface-muted` | The evidence is not sufficient to answer |
| Nguồn xung đột (Conflicting sources) | alert-octagon | `--color-danger` on `--color-danger-bg` | The sources say different things, and a person with authority needs to verify |
| Chưa tìm thấy tài liệu được phép truy cập (No document you are allowed to access was found) | lock or search | neutral | There is no document inside the user's rights; do not reveal that one exists |

**Node effectivity by application date**

| `amendment_state` | Vietnamese label | Icon | Color |
|---|---|---|---|
| `active` | Đang áp dụng tại [ngày] (In application on [date]) | check-circle | success |
| `modified` | Đã sửa đổi từ [ngày] (Amended from [date]) | file-pen | warning |
| `repealed` | Đã bãi bỏ từ [ngày] (Repealed from [date]) | ban | danger |
| `suspended` | Tạm đình chỉ (Temporarily suspended) | pause-circle | warning |
| `not_yet_effective` | Chưa có hiệu lực (Not yet in effect) | clock | evidence (light blue) |
| `unknown` | Hiệu lực chưa xác minh (Effectivity not yet verified) | help-circle | neutral |

When `as_of_date` is before the amendment date, use the sentence: "Quy định được thay đổi từ [ngày] (sau ngày tra cứu). Cần xem quy định chuyển tiếp." (The provision is changed from [date] (after the search date). Transitional provisions need to be reviewed.) Do not say the old version certainly does not apply.

**Coverage-checklist items**

| Item | Display label |
|---|---|
| `source_verified` | Nguồn và trích dẫn đã kiểm tra (Source and citation checked) |
| `effective_checked` | Hiệu lực tại ngày áp dụng (Effectivity on the application date) |
| `applicability_checked` | Điều kiện áp dụng (Conditions of application) |
| `claim_supported` | Nhận định có căn cứ hỗ trợ (The finding is supported by evidence) |
| `transition_checked` | Quy định chuyển tiếp (Transitional provisions) |
| `required_facts_complete` | Dữ kiện bắt buộc (Required facts) |
| `scope_expansion` | Mở rộng ngoài phạm vi đúng chính sách (Expansion outside the scope follows policy) |

Each item has 3 statuses: **Đạt** (Met) (check) · **Chưa đạt** (Not met) (x) · **Chưa xác minh** (Not yet verified) (help). The default display is collapsed, "Đã kiểm tra X/Y mục" (Checked X of Y items), and it can be expanded.

The current API uses the checklist names in the table above and the enum `passed / failed / unknown`. Do not use a boolean to force “chưa xác minh” (not yet verified) into false. `effective_status_checked` / `node_effective_checked` are old names and are not emitted by API v1.3. `claim_supported=passed` requires the defined support checks to be sufficient. Passing only figures or negation is not treated as proof of the finding's meaning.

**Ingest jobs:** Chờ (Waiting) · Đang đọc trang (Reading the page) · Phân tích cấu trúc (Analyzing structure) · Cần duyệt (Needs review) · Lỗi (Error) · Đã hủy (Cancelled) · Xong (Done). **AI suggestions:** Đề xuất (Suggested) · Đã chấp nhận (Accepted) · Đã từ chối (Rejected) · Hết hạn (Expired). **Gold case:** Nháp (Draft) · Đã duyệt (Approved) · Cần sửa (Needs changes) · Loại bỏ (Discarded).

### D.8 Interface copy (microcopy)

Principles: plain Vietnamese, active voice, and a statement of what will actually happen. An error states **what happened and how to handle it**. It does not offer a generic apology. An empty state leads to the next action.

| Context | Copy |
|---|---|
| Question-field placeholder | "Mô tả tình huống hoặc hỏi về một Điều, Khoản…" (Describe a situation, or ask about an Article or a Clause…) |
| Send button | "Tra cứu" (Search) |
| Button after facts are edited | "Cập nhật dữ kiện & Tra cứu lại" (Update facts and search again) |
| Dirty bar | "Đã chỉnh sửa dữ kiện — kết quả bên dưới dựa trên dữ kiện trước đó" (Facts have been edited — the results below are based on the previous facts) |
| Phase 1 skeleton | "Đang tìm căn cứ trong danh mục đã chọn…" (Searching for evidence in the selected category…) |
| Phase 2 | "Đã tìm thấy và kiểm tra nguồn của [X] căn cứ. Đang phân tích điều kiện áp dụng, hiệu lực, quy định chuyển tiếp và ngoại lệ…" (Found and checked the source of [X] pieces of evidence. Analyzing conditions of application, effectivity, transitional provisions, and exceptions…) |
| Sentence as understood | "Đang hiểu là: “…”" (Understood as: “…”) + the button "Sửa" (Edit) |
| Insufficient evidence | "Chưa đủ căn cứ để trả lời. Các tài liệu được phép truy cập chưa có quy định phù hợp với câu hỏi này." (The evidence is not sufficient to answer. The documents you are allowed to access do not yet contain a provision that fits this question.) |
| Not found / no right | "Chưa tìm thấy tài liệu được phép truy cập." (No document you are allowed to access was found.) |
| False premise | "Không có [Điều X] trong [tên văn bản]. Văn bản này có Điều 1 đến Điều [N]." (There is no [Article X] in [administrative-document name]. This administrative document has Article 1 through Article [N].) |
| Explanation error | "Giải thích tạm thời không khả dụng. Các căn cứ bên dưới đã được kiểm tra nguồn." (Explanation temporarily unavailable. The evidence below has had its source checked.) |
| Stale snapshot | "Dữ liệu hiệu lực đang được cập nhật. Chưa thể khẳng định hiệu lực tại ngày này." (Effectivity data is being updated. Effectivity on this date cannot be asserted yet.) |
| Old result | "Kết quả dựa trên dữ kiện trước đó" (Result based on the previous facts) · "Cần kiểm lại vì dữ liệu hiệu lực đã thay đổi" (Needs recheck because the effectivity data has changed) |
| Viewer fallback | "Chưa tô sáng chính xác vị trí đoạn này trên trang." (The position of this passage on the page has not been highlighted precisely.) |
| Amendment banner | "Khoản này trên PDF gốc đã được sửa đổi/bãi bỏ bởi [văn bản] từ ngày [ngày]." (This clause on the original PDF was amended/repealed by [administrative document] from [date].) + "Xem văn bản sửa đổi" (View the amending administrative document) |
| Effectivity not clear | "Hiệu lực chưa xác minh. Hệ thống chưa kết luận khoản này còn hay hết hiệu lực." (Effectivity is not yet verified. The system has not concluded whether this clause is still in effect or no longer in effect.) |
| Source outside the category | "Nguồn ngoài danh mục đã chọn" (Source outside the selected category) |
| Copy | "Sao chép kèm phạm vi" (Copy with scope) → the announcement "Đã sao chép, kèm phạm vi và cảnh báo." (Copied, including the scope and the warning.) |
| Notice at the end of a result | "Kết quả hỗ trợ tra cứu và tham mưu, không thay thế quyết định của người có thẩm quyền." (The result supports search and is advisory (tham mưu). It does not replace (thay thế) the decision of the person who has authority.) |
| Feedback | "Căn cứ sai" (Wrong evidence) · "Thiếu căn cứ" (Missing evidence) · "Văn bản hết hiệu lực" (Administrative document no longer in effect) · "Trích dẫn sai đoạn" (Wrong cited passage) |
| Domain blocked | "Tên miền này chưa nằm trong danh sách cho phép. Nhờ quản trị viên thêm tên miền sau khi xác minh." (This domain is not yet on the allowlist. Ask an administrator to add the domain after verification.) |
| Revision conflict | "Mục này vừa được người khác sửa. Tải lại để xem thay đổi." (Someone else just edited this item. Reload to see the change.) |
| Effectivity confirmation | "Thay đổi này ảnh hưởng cách hệ thống trả lời với các ngày từ [ngày]. Hành động được ghi nhật ký." (This change affects how the system answers for dates from [date]. The action is written to the log.) → "Duyệt" (Approve) / "Quay lại" (Go back) |
| Delete memory | "Xóa toàn bộ bộ nhớ của bạn? Hành động này không hoàn tác." (Delete all of your memory? This action cannot be undone.) → "Xóa bộ nhớ" (Delete memory) / "Giữ lại" (Keep it) |
| Not-stored mode | "Hội thoại này sẽ không được ghi nhớ." (This conversation will not be remembered.) |
| Memory (explanation) | "Bộ nhớ giúp trợ lý hiểu câu hỏi nối tiếp. Câu trả lời luôn lấy căn cứ lại từ kho tài liệu." (Memory helps the assistant understand a follow-up question. The answer always fetches evidence again from the document repository.) |
| Empty category | "Danh mục chưa có tài liệu đã duyệt. Nhờ người phụ trách nạp tài liệu." (The category does not yet have an approved document. Ask the person responsible to ingest documents.) |
| Connection lost | "Mất kết nối tới máy chủ. Nội dung bạn nhập vẫn được giữ." (Connection to the server was lost. What you entered is still kept.) + "Thử lại" (Retry) |
| Local Mode badge | "Local Mode · offline" (tooltip: "Mọi xử lý chạy trên máy chủ nội bộ, không gửi dữ liệu ra ngoài." (All processing runs on the internal server. Data is not sent outside.)) |
| API Mode badge | "API Mode" (tooltip: "Chỉ dữ liệu được chính sách cho phép mới được gửi tới nhà cung cấp AI." (Only data the policy allows is sent to the AI provider.)) |

Forbidden in the interface: "Đã khóa X căn cứ xác thực" (Locked X pieces of authentic evidence), "Đã xác minh X căn cứ" (Verified X pieces of evidence) (when effectivity and coverage have not been proven), an accuracy percentage, "chắc chắn" (certain), "AI đảm bảo" (the AI guarantees).

### D.9 Accessibility and interface performance

**Accessibility (WCAG 2.2 AA at minimum)**

- Every function can be operated with the keyboard. Focus order follows reading order. Focus is always visible (3px, offset 2px).
- Chat Agent: the launcher is a `button`. The panel is `role="dialog"` and **not modal** (`aria-modal="false"`) when docked, with `aria-labelledby` pointing at the title. Opening the panel moves focus into the input. `Esc` closes it and returns focus to the launcher. Focus is not trapped except when the panel is full screen on a phone. The stream sits in a region `aria-live="polite"`, and it announces only important milestones (evidence is available, a result is available). It does not read every token.
- Touch targets are at least 44×44px on a phone. Zoom to 200% is supported without losing function. There is no horizontal scroll at 320px.
- Color is not the only signal. A chart has an alternative data table.
- `prefers-reduced-motion` turns off slide and fade motion.
- Vietnamese content with diacritics displays correctly. The attribute is `lang="vi"`. Copied text includes the source.

**Interface performance**

- The launcher costs almost nothing on page load: the panel bundle, the PDF viewer, and charts **load lazily** (code-splitting). Prefetch on launcher hover, or when the user types in the question field.
- The PDF viewer is built page by page (virtualized). It renders only the page being viewed and its neighbors. Prefetch the cited page on hover of `[n]`.
- A long list (documents, the queue, Gold cases) uses pagination or virtual scrolling.
- Local Mode: do not load a resource from outside (CDN, font, analytics, telemetry).
- The page-load budget is measured before and after the widget is added (WP 4.7). Do not state a number before it is measured.

### D.10 Interface testing (mandatory)

- **Image snapshots** for: effectivity statuses (`active/modified/repealed/suspended/not_yet_effective/unknown`), result labels (4 plus not-found), FactChip (3 kinds plus dirty), the Sticky Amendment Banner (open / collapsed), EvidenceCard, the Chat Agent panel (closed / open / minimized / phone), the two-phase skeleton, and the viewer fallback.
- **An automatic contrast test** for every color pair and status (tokens). If it does not pass, adjust the token.
- **Lint** forbids hardcoded HEX in a component.
- **An automatic accessibility check** (axe or equivalent) on every screen, plus a manual keyboard and screen-reader check for S1, S3, and S6.
- **E2E:** flows L-1 through L-7 (C.11). Local Mode produces no request to the outside. Moving between pages keeps the conversation. Opening an old citation rechecks rights.
- **Copy:** a test that the forbidden strings in D.8 do not appear in the bundle.
- **Desktop USER:** a real check of login → Orb → chat → PDF/workspace → collapse/open → tray → logout/exit. The Orb is round, with no square background and no stray shadow. The login and panel backgrounds are opaque. The drag region does not cover text. Resize works. There is no console. Check DPI at 100/125/150/200%, a monitor or work-area change, 200% zoom, the widths 320/768/1024/1280px, and collapse/open without losing content.
