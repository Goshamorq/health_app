# health_app — MVP spec

## Goal

Help me (single user) improve sleep, sport, and eating habits by turning daily self-tracking into a gentle, gamified routine that takes ≤60 seconds per check-in.

Success = I open the app daily for ≥4 weeks and notice patterns I would have missed without it.

## Non-goals

- Multiple users / accounts / sharing
- Cloud sync / mobile app
- Calorie counting, macros, structured food logging
- Medical-grade tracking, integrations with Apple Health (deferred)
- Notifications / reminders (deferred)
- Quests, badges, avatars (deferred)
- Correlation analysis / ML insights (deferred)

## Users

One: project owner. Localhost only. No auth.

## Core mental model

Three **pillars**: `sleep`, `sport`, `food`.

Each pillar has a set of **habits**. A habit has a **type**:

- `binary` — yes/no (e.g., "in bed by 23:30")
- `time` — record a time of day (e.g., "lights out at __:__")
- `quantity` — numeric value with bucketed thresholds (e.g., steps: <5k / 5–7k / 7–10k / 10–15k / 15k+)

Each habit defines its own thresholds for what counts as "done":
- `binary` → done = true
- `time` → done if time ≤ target (or ≥, configurable per habit)
- `quantity` → done if value ≥ a configured threshold bucket

A **daily check-in** records the state of every habit + a few global fields for that date.

## Features

### 1. Daily check-in (the hub)

A single screen for today. Sections:

**Per pillar (sleep / sport / food):** rows of habits with the appropriate input (checkbox, time picker, or bucket selector).

**Global fields:**
- Sleep duration (hours, numeric)
- Sleep quality 1–5
- Energy/mood AM 1–5
- Energy/mood PM 1–5
- Water: low / mid / good
- Steps bucket: <5k / 5–7k / 7–10k / 10–15k / 15k+
- Caffeine today: yes/no
- Alcohol today: yes/no
- Late meal (after 21:00): yes/no
- Food (free text, multi-line)
- Daily note (free text)

**Friction reducers:**
- "As yesterday" button — copies the previous day's check-in into today, user tweaks what changed.
- Edit any past date (not just today) via date picker.

### 2. Habits management

A settings screen to:
- Add / edit / archive habits per pillar
- Set type (binary / time / quantity) and threshold
- Preset on first run: a small starter set across all three pillars (concrete habits to be decided during build).

### 3. Trigger journal

Separate from daily notes. A list of entries created when something derailed me. Each entry: timestamp, free-text description, optional tag (e.g., `stress`, `social`, `boredom`).

### 4. Weekly review

A simple screen, accessible any time but featured on Sundays. Shows the last 7 days:
- Average sleep hours, sleep quality
- Daily score average
- Streak status per habit
- Aggregated AM/PM mood
- Days with caffeine / alcohol / late meal count
- Free text field: "Notes for next week"

### 5. Gamification

- **Daily score** 0–100 = (habits completed today) / (active habits today) × 100. Shown on the hub.
- **Streak** per habit: consecutive days "done". **Forgiveness rule:** 1 missed day per rolling 7 does not break the streak. ≥2 missed days within 7 → streak resets.

### 6. Visualisation

- **Today hub:** daily score, current streak per habit, last 7 days mini-strip.
- **Heatmap calendar (30 days)** per pillar: each cell colored by % of pillar's habits done that day.

## Data model (sketch)

```
habits(id, pillar, name, type, threshold_config_json, archived, created_at)
checkins(date PRIMARY KEY, sleep_hours, sleep_quality, mood_am, mood_pm,
         water_bucket, steps_bucket, caffeine, alcohol, late_meal,
         food_text, note_text, updated_at)
habit_entries(checkin_date, habit_id, value_json, done BOOL, PRIMARY KEY(checkin_date, habit_id))
trigger_entries(id, ts, text, tag)
weekly_reviews(week_start_date PRIMARY KEY, notes_text)
```

All in one SQLite file: `data/health.db`.

## Tech stack

- **Backend:** Python 3.12 + FastAPI
- **Templates:** Jinja2
- **Frontend interactivity:** HTMX + Alpine.js (no build step)
- **Storage:** SQLite via stdlib `sqlite3` (no ORM unless friction shows up; SQLAlchemy as fallback)
- **Migrations:** plain `.sql` files in `migrations/`, applied at startup if newer than schema_version
- **Charts:** server-rendered SVG for heatmap (no JS chart lib for MVP)
- **Run:** `uvicorn` on `localhost:8765`, bound to 127.0.0.1 only
- **Process management:** later — `launchd` agent to start at login. Not in MVP.

## Project layout (proposed)

```
health_app/
├── app/
│   ├── main.py            # FastAPI app, routes
│   ├── db.py              # sqlite connection + migrations runner
│   ├── models.py          # dataclasses / typed dicts
│   ├── scoring.py         # daily score + streak logic
│   ├── routes/            # routes split by feature
│   └── templates/         # Jinja2 templates
│       ├── base.html
│       ├── hub.html
│       ├── habits.html
│       ├── trigger.html
│       └── weekly.html
├── static/                # CSS, htmx, alpine
├── migrations/            # 001_init.sql, 002_*.sql ...
├── data/                  # health.db (gitignored)
├── docs/
│   └── spec.md            # this file
├── pyproject.toml
└── README.md
```

## Out of scope (backlog, in rough priority)

1. Apple Health import (manual CSV first, then HealthKit via small Swift sidecar later)
2. Correlation insights ("you sleep worse after late meals")
3. Native macOS notifications / `launchd` autostart
4. Quests (e.g., "no caffeine after 16:00 for 7 days")
5. Achievement badges
6. Avatar / character
7. Mood trend charts
8. Mobile / responsive polish

## Open questions

- Exact starter habits per pillar — decide during build, not blocking.
- Where weekly review lives in nav vs. just appearing on hub on Sundays.
- Backup story for `health.db` — likely just rely on Time Machine; revisit if it bites.
