# Design system — Self-creation

Single source of truth for visual + interaction decisions. Normative
("MUST", "NEVER"). When in doubt: read this first, then code.
Values shown here come from [static/app.css](../static/app.css) — that
file is the canonical implementation, this doc is the canonical intent.

---

## 1. Principles

- **Calm over clever.** Soft shadows, muted slate, generous whitespace.
  No harsh shadows, no glows, no animations beyond 120 ms.
- **Data dominates ornamentation.** Colored cells (pillar hues, scores)
  ALWAYS read over decorative bg (weekend stripes, month dividers).
- **Forgiving by default.** Confirms on destructive actions; allow undo
  paths (archive instead of delete; reset clears, doesn't damage).
- **One thing per row.** Inline edit replaces view, doesn't sit beside.

---

## 2. Color tokens

All in `:root` of [static/app.css](../static/app.css). MUST reference
via `var(--…)`; NEVER hardcode hex.

| Token | Hex / RGB | Use |
|---|---|---|
| `--bg` | `#F8FAFC` | Page background |
| `--surface` | `#FFFFFF` | Card background |
| `--surface-2` | `#F1F5F9` | Sidebar active, inputs, subtle fills |
| `--border` | `#E2E8F0` | Hairlines, input borders |
| `--text` | `#0F172A` | Primary text |
| `--muted` | `#64748B` | Secondary text, dividers, weekend stripe |
| `--accent` | `#10B981` | Primary action, "done" state, ≥67 % score |
| `--accent-hover` | `#059669` | Primary button hover |
| `--accent-soft` | `#D1FAE5` | Focus ring on inputs |
| `--warn` | `#F59E0B` | 34–66 % score band, "other" stars |
| `--bad` | `#EF4444` | <34 % score band, delete-hover, overdue |

Score band rule:
- `score >= 67` → `--accent`
- `34 ≤ score < 67` → `--warn`
- `1 ≤ score < 34` → `--bad`
- `score == 0` → `--muted` (empty)

---

## 3. Pillar palette

Stored as space-separated RGB triplets (so we can compose with alpha).
MUST use the `pillar-X` class on heatmap cells; opacity stack:

| Pillar | RGB | Hint |
|---|---|---|
| `--pillar-sleep` | `100 116 139` | Slate (gray) |
| `--pillar-sport` | `59 130 246` | Blue |
| `--pillar-food` | `16 185 129` | Emerald (= `--accent`) |
| `--pillar-other` | `245 158 11` | Amber (= `--warn`) |

Heatmap intensity scale:
- Pillar summary cell: `1 → 0.45`, `2 → 0.75`, `3 → 1.0` alpha
- Habit cell (drilldown, done): `0.55` alpha
- Empty cell: `rgb(100 116 139 / 0.10)` (faint slate)
- Weekend stripe behind: `rgb(100 116 139 / 0.14)`

---

## 4. Typography

- Family: **Inter**, self-hosted, weights 400 / 500 / 600 only.
  Fallback: `system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`.
- Body: 14 px / 1.5.
- `h1`: 28 px / 600 / `-0.01em` tracking.
- `h2`: 18 px / 600.
- `.label-eyebrow`: 12 px / 500 / uppercase / `0.06em` tracking / `--muted`.
- `.muted`: same color (`--muted`), regular weight.
- Numbers MUST use `font-variant-numeric: tabular-nums` for alignment
  (timestamps, scores, dates).

NEVER use Inter weights other than 400/500/600. NEVER use italic.

---

## 5. Spacing & radii

- Scale: **4 / 8 / 12 / 16 / 24 / 32 px**. NEVER 5, 7, 10, 18, 22.
- Card padding: 20 px.
- Section gap between cards: 12–16 px.
- `--radius`: **12 px** (cards, big blocks).
- `--radius-sm`: **6 px** (buttons, inputs, pills, small tiles).
- Heatmap cell radius: **2 px**.
- Heatmap active-column contour radius: **5 px**.

Shadows (NEVER use other shadow recipes):
- `--shadow`: `0 2px 8px rgba(15, 23, 42, .06)` — default card resting.
- `--shadow-hover`: `0 4px 16px rgba(15, 23, 42, .10)` — reserved for
  future hover lift; currently unused.

---

## 6. Components

### Button

| Variant | Class | When |
|---|---|---|
| Primary | `button.primary` or `.btn-primary` | Single most-likely action per view: Save, Add habit, Done. |
| Ghost | `.btn-ghost` | Secondary actions: Cancel, Reset, Copy, Edit, Restore, toggles. |

MUST: one primary per visible card (max). MUST: confirm dialog
(`onclick="return confirm(…)"` or `hx-confirm`) on every destructive
action (delete, reset, overwrite).

NEVER use a primary button to delete or reset.

### Card (`.block` / `.card`)

White surface, 1 px `--border`, 12 px radius, 20 px padding, `--shadow`.
`h2` inside a card is rendered as 12 px uppercase eyebrow.

### Input / textarea / select

8 × 10 px padding, 1 px `--border`, 6 px radius, `--surface` bg.
Focus: 3 px `--accent-soft` ring + `--accent` border.

### Pill (rating / bucket)

`.rating label` and `.bucket label` wrap a hidden `<input type="radio">`.
Selected: `--accent` fill, white text. Hover: `--surface-2` bg.

### Sidebar nav item

220 px sidebar, 14 px font, 10 px padding, 3 px left border (transparent
default → `--accent` when active). Active item also gets `--surface-2`
bg and `--accent` text. Icon MUST be inline SVG (see §9).

### Heatmap cell

14 × 14 px, 2 px radius, flex-aligned with 2 px gap. Habit cells
visually scaled `transform: scale(0.72)` so the layout slot stays
aligned with pillar cells. Active day: rounded contour on the bg-col
spanning the whole column (`outline 1 px solid var(--muted)`,
`outline-offset 1 px`, `border-radius 5 px`).

---

## 7. Layout patterns

- **App shell.** `display: grid; grid-template-columns: 220px 1fr; min-height: 100vh`.
  Sidebar left, main content right (max-width 960 px, padding 32 px).
- **Sticky save bar** (check-in): single card pinned `top: 8 px` inside
  the form, holds the only Save button. MUST be the only Save affordance.
- **Date nav header** (check-in, weekly): `←` arrow, big clickable date
  (`.date-h1` triggers native picker via `showPicker()`), `→` arrow,
  optional "Today" link, flex spacer, action buttons (Reset / Copy).
- **Empty states.** Muted-text paragraph inside the card; NEVER full-card
  illustrations.
- **History sections.** Collapsed by default via `<h2 @click="open=!open">`
  with Alpine `x-show`. Chevron via `▸ / ▾` unicode glyphs.

---

## 8. Interaction patterns

- **Inline edit toggle.** Each editable row uses Alpine `x-data="{editing: false}"`.
  View block (`x-show="!editing"`) and form (`x-show="editing" x-cloak`) are
  siblings. NEVER a modal for inline edit.
- **HTMX partial swaps.** List mutations (trigger / notes / habits) POST
  to an endpoint that returns the same `_list.html` partial; client swaps
  `#…-list` `innerHTML`. NEVER full page reload for in-list edit/delete.
- **Confirm before destructive.** Native `confirm()` (or `hx-confirm`).
  Wording MUST name the target ("Delete entry for 2026-05-19?").
- **Hover affordance.** Heatmap cells scale `1.4×`; habit cells scale to
  `1.1×` (from base 0.72). Pillar links: `transform: translateY(-2px)`.
- **localStorage for ephemeral view state.** Heatmap drilldown open/closed
  is persisted under `hm-pillar-{sleep|sport|food|other}`. NEVER use
  cookies. NEVER store on server.
- **URL params for shareable / restorable state.** Date selection
  (`?date=`), week selection (`?week=`). Internal Alpine `x-data` only
  for transient state.

---

## 9. Iconography

- **Inline SVG only.** Heroicons-style outline, `stroke="currentColor"`,
  `stroke-width="2"`, `stroke-linecap="round"`, `stroke-linejoin="round"`,
  20 × 20 viewBox.
- NEVER an icon library / icon font / sprite sheet. Total icons in app
  ≤ 10; each one inline in the template that uses it.

Unicode glyphs allowed: chevrons (`▸ ▾ ▴ ▾`), arrows (`← →`), star
(`★`), cross (`×`), check-mark (`✓`), pencil (`✎`).

---

## 10. Anti-features (NEVER add without explicit ask)

- Dark mode / theme toggle / `prefers-color-scheme` branch.
- Icon library (Lucide, Heroicons npm, Font Awesome).
- Chart library (Chart.js, D3, Recharts). All viz is HTML divs + inline SVG.
- Modals / dialogs / popovers (use inline expand instead).
- HTMX `hx-boost` for full-page nav (would break Alpine state per page).
- Animations beyond 120 ms opacity / transform.
- Tooltips beyond native `title` attribute.
- Toast notifications (use `?saved=1` banner inside the page instead).
- Color outside the 11 tokens + 4 pillar hues above.

---

## 11. When tokens change

If a value is added or changed in `:root` of `static/app.css`, this doc
MUST be updated in the same commit. Treat the doc as production code —
drift is a bug.
