# Implementation plan: health_app MVP

## Overview

Build the MVP described in [spec.md](spec.md). Slice vertically: each phase ends with a working, usable app, even if features are missing. First usable check-in by end of Phase 2.

## Architecture decisions

- **Stack:** Python 3.12 + FastAPI + Jinja2 + HTMX + Alpine.js + SQLite (stdlib `sqlite3`). No ORM, no JS build step. Rationale: minimum moving parts for a solo project; if friction shows up later, swap in SQLAlchemy.
- **Migrations:** plain `.sql` files in `migrations/`, applied at startup via a `schema_version` table. Forward-only. Rationale: trivial to write and audit by hand.
- **Day boundary:** the local date at request time. Late-night logging (past midnight) lands on the new day — user can use the date picker to backfill yesterday. Rationale: simpler than custom 04:00 cutoffs.
- **Server-rendered everything.** HTMX swaps fragments for interactivity. No client-side state beyond Alpine for trivial UI toggles.
- **Heatmap as inline SVG**, rendered by FastAPI from query results. No charting library.

## Risks and mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Streak-with-forgiveness logic has off-by-one or timezone bugs | Med | Unit-test `streak()` and `daily_score()` in isolation; fixture-driven test of 10–15 day windows |
| HTMX/Alpine ergonomics new and slow at start | Low | Phase 1 builds one tiny HTMX swap to validate the pattern before committing |
| Time-type habit thresholds ambiguous (is "in bed by 23:30" ≤ or ≥?) | Low | Threshold config carries a `direction: "before" \| "after"` field |
| Habit schema change after starter habits are in | Low | Threshold stored as JSON blob — additive changes cheap |
| Daily score formula doesn't reflect "real" health progress | Med | Out of scope to solve in MVP; revisit after 2–4 weeks of real use |

## Open questions

- Exact starter habit list per pillar — decide in Task 4 (Habits CRUD + seed). Not blocking earlier work.
- Whether weekly review pops up automatically on Sundays or only lives in nav — defer to Phase 5.

---

## Phase 1 — Foundation

### Task 1: Project scaffolding

**Description:** Create the FastAPI project skeleton, dependency manifest, run script, and `.gitignore`. App serves a static "Hello" page at `/` on `localhost:8765`.

**Acceptance criteria:**
- [ ] `pyproject.toml` with `fastapi`, `uvicorn[standard]`, `jinja2` as deps
- [ ] `app/main.py` with FastAPI app, one route `GET /` returning HTML "Hello health_app"
- [ ] `scripts/run.sh` launches uvicorn on `127.0.0.1:8765`
- [ ] `.gitignore` covers `agent-skills/`, `data/`, `__pycache__/`, `.venv/`, `*.db`

**Verification:**
- [ ] `bash scripts/run.sh` starts the server
- [ ] `curl http://127.0.0.1:8765/` returns the hello page
- [ ] Open in browser — page renders

**Dependencies:** None
**Files likely touched:** `pyproject.toml`, `app/main.py`, `scripts/run.sh`, `.gitignore`
**Scope:** S

### Task 2: SQLite + migrations runner + initial schema

**Description:** Connection helper, migration runner applied on startup, and the initial schema covering all tables in the spec.

**Acceptance criteria:**
- [ ] `app/db.py` exposes `connect()` returning a `sqlite3.Connection` to `data/health.db` with `row_factory=sqlite3.Row` and `PRAGMA foreign_keys=ON`
- [ ] `app/db.py` has `apply_migrations()` that reads `migrations/*.sql` in order and applies any not yet recorded in `schema_version(version INTEGER PRIMARY KEY, applied_at TEXT)`
- [ ] `migrations/001_init.sql` creates: `habits`, `checkins`, `habit_entries`, `trigger_entries`, `weekly_reviews` per the schema in [spec.md](spec.md)
- [ ] Migrations run automatically on FastAPI startup via `lifespan`

**Verification:**
- [ ] Start server, `data/health.db` is created
- [ ] `sqlite3 data/health.db ".schema"` shows all 5 tables + `schema_version`
- [ ] Restart server — no errors, no duplicate migration

**Dependencies:** Task 1
**Files likely touched:** `app/db.py`, `app/main.py`, `migrations/001_init.sql`
**Scope:** M

### Task 3: Base template + static assets

**Description:** Jinja2 base layout with nav, HTMX + Alpine loaded from local static, minimal CSS. Index route now extends base.

**Acceptance criteria:**
- [ ] `app/templates/base.html` with `<head>` linking `/static/htmx.min.js`, `/static/alpine.min.js`, `/static/app.css`; `<body>` has nav (Hub / Habits / Trigger / Weekly placeholders) and `{% block content %}`
- [ ] `static/` contains downloaded HTMX, Alpine, and `app.css` with a minimal reset
- [ ] FastAPI mounts `StaticFiles` at `/static`
- [ ] `GET /` renders `hub.html` extending `base.html` with placeholder "Hub coming soon"
- [ ] One smoke HTMX swap: a button on the hub that GETs `/ping` and swaps a div with the response

**Verification:**
- [ ] Page loads with no 404s in network tab
- [ ] Clicking the button updates the div via HTMX (no full reload)

**Dependencies:** Task 1
**Files likely touched:** `app/main.py`, `app/templates/base.html`, `app/templates/hub.html`, `static/*`
**Scope:** S

### Checkpoint: Foundation
- [ ] Server starts, DB initializes, page renders, HTMX works
- [ ] Manual sanity check in browser

---

## Phase 2 — Core check-in slice

### Task 4: Habits CRUD + seed

**Description:** Page to view, add, edit, archive habits per pillar. Seed a starter set on first run. Decide the starter list during this task (3–5 habits per pillar).

**Acceptance criteria:**
- [ ] `GET /habits` lists active habits grouped by pillar; archived collapsed
- [ ] Form to add a habit: pillar (select), name, type (`binary`/`time`/`quantity`), threshold config (form fields shown conditionally by type via Alpine)
- [ ] Threshold config stored as JSON: binary `{}`; time `{"target": "23:30", "direction": "before"|"after"}`; quantity `{"buckets": [5000, 7000, 10000, 15000], "min_done_bucket": 2}` (index into buckets)
- [ ] Edit and archive actions (HTMX patch in-place, no full reload)
- [ ] On first startup, if `habits` table is empty, insert starter habits

**Verification:**
- [ ] Add, edit, archive each habit type; reload page — state persisted
- [ ] DB row matches what the form submitted

**Dependencies:** Task 2, Task 3
**Files likely touched:** `app/routes/habits.py`, `app/templates/habits.html`, `app/main.py`, possibly `migrations/002_seed.sql` or seed in `db.py`
**Scope:** M

### Task 5: Hub — today's check-in form + save

**Description:** The main daily-use screen. Renders global fields and habit rows for today's date, persists to `checkins` and `habit_entries` on submit. No score/streak yet.

**Acceptance criteria:**
- [ ] `GET /` shows today's date and a form with: sleep hours, sleep quality (1–5 picker), mood AM (1–5), mood PM (1–5), water bucket (3 radio), steps bucket (5 radio), caffeine/alcohol/late_meal checkboxes, food textarea, daily note textarea
- [ ] Below the global section: each active habit rendered with its input widget (checkbox / time picker / bucket radio matching threshold buckets)
- [ ] "Save" persists to `checkins(date=today)` (upsert) and `habit_entries(checkin_date=today, habit_id, value_json, done)` (upsert)
- [ ] `done` computed server-side from `value_json` against the habit's threshold config
- [ ] After save, page re-renders with values prefilled

**Verification:**
- [ ] Fill form, save, reload — values prefilled correctly
- [ ] `sqlite3` query shows correct rows
- [ ] Try each habit type and verify `done` is computed correctly (binary true/false, time before/after target, quantity meets `min_done_bucket`)

**Dependencies:** Task 4
**Files likely touched:** `app/routes/hub.py`, `app/templates/hub.html`, `app/scoring.py` (just `is_done()` helper for now)
**Scope:** M

### Task 6: "As yesterday" + edit past dates

**Description:** Friction reducers: one-click copy from previous day, and date picker to edit any past date.

**Acceptance criteria:**
- [ ] "As yesterday" button on hub copies the most recent prior `checkins` row + its `habit_entries` into today (skip if today already has any data — show confirm)
- [ ] Date picker in hub header navigates to `GET /?date=YYYY-MM-DD`; form renders that date's data and saves to that date
- [ ] If a habit was added after a past date, it appears empty (not "missed") on that date

**Verification:**
- [ ] Save yesterday → click "As yesterday" on empty today → today populated identically
- [ ] Navigate to a date 10 days ago, edit, save, reload — persisted
- [ ] Confirm flow when today already has data

**Dependencies:** Task 5
**Files likely touched:** `app/routes/hub.py`, `app/templates/hub.html`
**Scope:** S

### Checkpoint: Core check-in usable
- [ ] I can log a real day in <60 seconds
- [ ] Past dates editable
- [ ] Start using it daily from this point (real dogfood)

---

## Phase 3 — Gamification

### Task 7: Daily score

**Description:** Compute and display today's daily score (0–100) and a per-pillar breakdown.

**Acceptance criteria:**
- [ ] `app/scoring.py::daily_score(conn, date)` returns `{total: int, by_pillar: {sleep: int, sport: int, food: int}}`
- [ ] Formula: per pillar, `done_habits / active_habits_on_date * 100`; total = average of pillar scores. Habits archived before that date excluded. Habit with no entry for that date counts as not-done.
- [ ] Hub shows: big total score + three small pillar scores
- [ ] Unit test for `daily_score` with fixture: 3 habits per pillar, mixed states

**Verification:**
- [ ] Tick all habits today → score 100
- [ ] Tick none → score 0
- [ ] Half done → score reflects it
- [ ] Unit test passes

**Dependencies:** Task 5
**Files likely touched:** `app/scoring.py`, `app/routes/hub.py`, `app/templates/hub.html`, `tests/test_scoring.py`
**Scope:** S

### Task 8: Streak with forgiveness

**Description:** Per-habit streak with rule: 1 missed day in any rolling 7-day window does not break the streak; 2+ missed days within 7 → resets.

**Acceptance criteria:**
- [ ] `app/scoring.py::streak(conn, habit_id, today)` returns int days
- [ ] Walks backward from `today`. Tracks misses in a rolling 7-day window. Stops when the window has ≥2 misses; returns days counted before that point.
- [ ] Hub shows current streak per active habit (chip with number)
- [ ] Unit tests: zero streak, perfect streak, one-miss forgiveness, two-misses break, edge case with gaps at the start

**Verification:**
- [ ] Create test data via SQL for known patterns and assert function output
- [ ] Visual check on hub matches manual count of recent days

**Dependencies:** Task 5, Task 7 (shared `scoring.py`)
**Files likely touched:** `app/scoring.py`, `app/routes/hub.py`, `app/templates/hub.html`, `tests/test_scoring.py`
**Scope:** M

### Checkpoint: Gamification
- [ ] Score and streaks visible on hub
- [ ] Logic unit-tested

---

## Phase 4 — Visualisation

### Task 9: 30-day heatmap per pillar

**Description:** Inline SVG heatmap on the hub, one strip per pillar, each cell = % of pillar's habits done that day, colored on a 5-step scale.

**Acceptance criteria:**
- [ ] `app/routes/hub.py` queries last 30 days of pillar-level completion %
- [ ] Renders 3 horizontal SVG strips (one per pillar), 30 cells each, with date tooltips via `<title>`
- [ ] Color scale: 0 = grey, 1–24 = pale, 25–49, 50–74, 75–100 = strongest. Pick colors from a single hue to stay calm.
- [ ] Today's cell highlighted with a thin border

**Verification:**
- [ ] After logging 5–10 days, heatmap reflects what was logged
- [ ] Hover shows date + score in tooltip

**Dependencies:** Task 7
**Files likely touched:** `app/routes/hub.py`, `app/templates/hub.html`, possibly `app/scoring.py` (bulk score query)
**Scope:** M

### Checkpoint: Visualisation
- [ ] Hub is informative at a glance

---

## Phase 5 — Notes layer

### Task 10: Trigger journal

**Description:** Standalone page to add and list trigger entries (timestamp + free text + optional tag).

**Acceptance criteria:**
- [ ] `GET /trigger` lists last 30 entries, newest first, with date, text, tag
- [ ] Form to add entry: text required, tag select (`stress`, `social`, `boredom`, `other`)
- [ ] `POST /trigger` inserts and re-renders list via HTMX swap
- [ ] Entries deletable (soft confirm)

**Verification:**
- [ ] Add 3 entries, delete one — list updates without reload

**Dependencies:** Task 3
**Files likely touched:** `app/routes/trigger.py`, `app/templates/trigger.html`, `app/main.py`
**Scope:** S

### Task 11: Weekly review

**Description:** Page showing last 7 days aggregates + a free-text "notes for next week" field stored per week.

**Acceptance criteria:**
- [ ] `GET /weekly` (default = current week, query `?week=YYYY-MM-DD` for past) shows: avg sleep hours, avg sleep quality, daily score avg, streak status per active habit, mood AM/PM avg, count of caffeine/alcohol/late_meal days
- [ ] Free-text "notes" textarea persists to `weekly_reviews(week_start_date)`
- [ ] Previous weeks navigable (prev/next links)

**Verification:**
- [ ] Aggregates match a manual SQL count
- [ ] Notes save and reload

**Dependencies:** Task 7, Task 8
**Files likely touched:** `app/routes/weekly.py`, `app/templates/weekly.html`, `app/main.py`
**Scope:** M

### Checkpoint: MVP complete
- [ ] All spec features land
- [ ] Real daily use for 2 weeks before deciding backlog priorities
