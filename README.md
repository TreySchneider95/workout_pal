# Workout Pal

A personal home-gym trainer and workout tracker. Open it on your phone, see today's workout, record what you lift, finish. It remembers exactly what you did last time and suggests when to move up in weight.

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2, Pydantic v2, Alembic, SQLite
- **Frontend:** React 19, TypeScript, Vite, Tailwind CSS v4, shadcn-style components (Radix), TanStack Query, Recharts, Lucide icons
- **Runs locally** with Docker Compose. No cloud services.

---

## Quick start

Requires Docker Desktop.

```bash
docker compose up --build
```

On first start the backend applies migrations and imports your exercise library and weekly plan from `seed/`.

| What | URL |
|---|---|
| App (this computer) | http://localhost:8080 |
| App (your phone, same Wi-Fi) | `http://<your-computer's-LAN-IP>:8080` (find the IP in System Settings → Wi-Fi → Details) |
| API docs (Swagger) | http://localhost:8080/api/docs (or http://localhost:8001/api/docs) |

Ports can be changed with `APP_PORT` and `API_PORT`, e.g. `APP_PORT=9000 docker compose up -d`.

**Tip:** on your phone, use the browser's “Add to Home Screen” for a full-screen app icon.

> **Security:** there are no user accounts. Only run this on a trusted home network and never expose port 8080 (or 8001) to the public internet, e.g. via router port forwarding. Use a VPN such as Tailscale if you want access away from home.

---

## Where your data lives

Everything is in the `data/` folder next to this README (mounted into the backend container at `/data`):

```
data/
  workout_pal.db          SQLite database (all workouts, sets, plan, settings)
  media/exercise-images/  exercise images (+ phone-sized thumbs/)
  backups/                automatic and manual backups
```

The data survives `docker compose down`, restarts and rebuilds. Only deleting `data/` removes it.

### Backups

```bash
# Consistent online backup to data/backups/ (safe while the app is running)
docker compose exec backend python -m app.cli backup
```

A backup is also taken automatically before every import. To restore, stop the app, copy a backup over `data/workout_pal.db`, and start it again:

```bash
docker compose stop backend
cp data/backups/workout_pal-YYYYMMDD-HHMMSS-manual.db data/workout_pal.db
rm -f data/workout_pal.db-wal data/workout_pal.db-shm
docker compose start backend
```

Copying the whole `data/` folder somewhere safe (e.g. iCloud Drive) is also a complete backup, as long as the app is stopped first.

---

## Your source data

`seed/` holds the files the app was built from:

| File | Purpose |
|---|---|
| `home_gym_exercises_verified.csv` | **Exercise library**: all 271 exercises your gym supports (IDs, muscle group, equipment, attachment, tracking type, per-side). |
| `home_gym_workout_with_images.zip` | **Weekly plan**: the schedule, sets (weeks 1–2 and week 3+), reps/duration, starting weights, weight conventions, pulley ratios, rest times, notes, and demonstration images. |

Exercise IDs (`EX0001`…) and image filenames come straight from these files. Custom exercises you add in the app get IDs `CX0001`….

### Importing / updating

Edit the CSVs (or drop in a new plan ZIP), then:

```bash
# Check first: validates everything and reports problems without saving
docker compose exec backend python -m app.cli import --check

# Import (takes a backup first)
docker compose exec backend python -m app.cli import
```

Options:

| Flag | Effect |
|---|---|
| `--library PATH` / `--plan PATH` | Use other files (paths inside the container, e.g. `/seed/new_plan.zip`). A plan can be a ZIP or a CSV with an `images/` folder next to it. |
| `--exercises-only` | Update exercises and images, but leave your workout templates exactly as you've edited them in the app. |
| `--no-library` / `--no-plan` | Import only one of the two sources. |
| `--profile NAME` | Whose workouts the plan updates (default: Trey). E.g. `--profile Abby --no-library --plan /seed/abby_plan.zip`. |

How the import behaves:

- **Idempotent.** Exercises are matched by ID and templates by session name (e.g. “Upper A”). Running it twice changes nothing.
- **Never touches workout history.** Recorded sessions and sets keep their own copy of what was prescribed.
- **All or nothing.** Any invalid row (unknown day, bad number, negative weight, unparseable reps…) aborts the whole import with a list of errors.
- **Images are checked.** Every referenced image is verified; missing or broken ones are reported, and the app shows a placeholder.
- **Plan templates are synced to the CSV.** Plan edits you made in the app to those templates (sets, order…) are replaced, except “skip temporarily” flags. Workouts you created yourself in the app are left alone. Use `--exercises-only` to keep all template edits.
- **Your equipment settings** (dumbbell list, increments) are never overwritten.

### Email (for AI plan prompts)

Optional. Copy `.env.example` to `.env`, fill it in and restart (`docker compose up -d`). With Gmail:
turn on 2-step verification, create an **app password** (Google Account → Security → App passwords),
and use it as `WORKOUT_SMTP_PASSWORD`. Each person adds their own address in **Settings**.
`.env` holds a password, so it's git-ignored; keep it that way.

---

## Using the app

**Profiles**: the app is shared by Trey and Abby. Each phone asks *Who's training?* once and remembers the answer; switch from the avatar on *Today* (or the bottom of the sidebar on desktop). Each person has their own weekly plan, workout history, weight suggestions, stats and settings. The exercise library and equipment are shared. Abby starts with no plan: build one from *Plan*, or log empty workouts.

**Today**: today's workout from your weekly plan, with estimated time and sets. On rest days you can still pick any workout, or an empty one. *Do a different workout* runs another day's workout without changing the schedule.

**Workout screen**:
- One exercise at a time, with the numbered dots at the top to jump around. Tap the image to see the full demonstration.
- Each card shows the target, rest time, the **weight convention** (e.g. *lb per dumbbell*, *lb plates · 2:1 pulley*, *lb added plates · bar not incl.*), and **what you did last time** for that exact exercise.
- Sets are prefilled with last time's weight and reps (or the plan's starting weight the first time). Use −/+ (dumbbells step through *your* available weights) or tap the number to type.
- Tap ✓ when a set is done. The rest timer starts automatically; it floats above the page and never blocks it. Use +15/−15, pause or skip.
- Per-side exercises get separate **L** and **R** rows. Timed holds have a built-in stopwatch. Cardio records minutes, miles and mph.
- **Every tap is saved immediately.** If the connection drops, changes are kept on the phone and sent when it's back (“Offline · kept on device”). A refresh or closed tab picks up exactly where you were.
- *Finish* asks for optional notes and saves the session to history.

**Weight suggestions** (per exact exercise; flat and incline bench never share history):
- First time: the plan's starting weight.
- All planned sets reached the top of the rep range: suggests the **next weight your equipment supports**.
- Average reps 2 or more below the range minimum (configurable): suggests one step lighter.
- Otherwise: stay at the current weight.
- Suggestions are **never applied automatically**; tap *Use 25 lb* to accept. Changing a default weight in the plan overrides history for the next session.

**Change with AI** (on *Plan*): describe what you want in plain words ("my knee hurts on lunges", "make it harder", "build me a 3-day plan"). The app writes a prompt for ChatGPT, Claude or Gemini with your current plan, recent weights, your equipment and dumbbells, every exercise in the library, and the exact JSON format to answer in. Copy it, download it, or email it to yourself. Paste the AI's whole reply back: the app finds the plan, checks every exercise ID, day and rep range against the library (rounding dumbbell weights to ones you own), and shows exactly what will change. Nothing is saved until you tap *Apply*, and the latest change can be undone. The AI's document is the *complete* plan: workouts it leaves out are removed. Past workouts are never affected. If the answer has problems, *Copy a message asking the AI to fix it* gives you a ready-made reply.

**Plan**: the 7-day schedule. Open a workout to reorder exercises (↑/↓), edit sets for weeks 1–2 and week 3+, reps or durations, default weight, rest and notes, skip an exercise temporarily, remove one, add any exercise from the library, or move the workout to another day (the two days swap). *New* builds a new workout from scratch or copies an existing one. Changes never alter past sessions.

**Exercises**: search and filter all 271 exercises by muscle group and equipment. Each exercise shows its image, equipment and attachment, weight convention, progress charts and full history. You can edit details, upload an image, mark one unavailable, or add custom exercises.

**History**: every completed workout. Open one to see every set, or tap *Edit* to correct sets, notes, date and times. Workouts can be reopened or deleted.

**Stats**: workouts this week, totals, consistency (planned days completed over 8 weeks), a 12-week calendar, workouts and training volume per week, per-exercise progress, and recent personal bests.

**Settings**: program start date (week 1 starts there; it's set automatically on your first workout), ramp-in weeks, rest timer behaviour, the suggestion threshold, and **your equipment**. Set the dumbbell weights you actually own, and the smallest plate jump for the cable stacks and Smith machine.

### Weight conventions

All weights are pounds, recorded exactly as entered and never reinterpreted:

| Convention | Meaning |
|---|---|
| lb per dumbbell | weight of **one** dumbbell (you hold two) |
| lb · one dumbbell | a single dumbbell (goblet squat, overhead extension) |
| lb plates · N:1 pulley | plates loaded on the cable stack; the pulley ratio is stored separately |
| lb added plates · bar not incl. | plates on the Smith bar only; bar weight not included |
| bodyweight · + added lb | bodyweight; optional added load |

Each recorded session stores the convention and pulley ratio it was performed with.

---

## Development

### Backend

```bash
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/alembic upgrade head          # create / migrate data/workout_pal.db
.venv/bin/python -m app.cli seed-if-empty
.venv/bin/uvicorn app.main:app --reload --port 8000
```

`WORKOUT_DATA_DIR` overrides the data folder (default `../data`).

### Frontend

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173, proxies /api and /media to :8000
# against the Docker backend instead:
VITE_BACKEND_URL=http://127.0.0.1:8001 npm run dev
```

### Tests

```bash
# Backend (pytest): importer, sessions, sets, history, progression, templates
cd backend && .venv/bin/python -m pytest
# ...or inside Docker
docker compose exec backend python -m pytest

# Frontend (vitest): autosave queue, steppers, set rows, exercise tracker
cd frontend && npm test
```

### Migrations

Migrations run automatically when the backend container starts. Manually:

```bash
docker compose exec backend alembic upgrade head
# after changing app/models.py (local dev):
cd backend && .venv/bin/alembic revision --autogenerate -m "describe change"
```

Back up before upgrading (`python -m app.cli backup`).

### Project layout

```
backend/
  app/
    models.py           tables: library, plan, history (history snapshots the plan)
    schemas.py          Pydantic request/response models
    routers/            /api/exercises, /equipment, /workout-templates, /workout-sessions, /history, /analytics, /dashboard, /settings
    services/
      importer.py       CSV/ZIP import + validation
      progression.py    previous performance + weight suggestions
      sessions.py       starting sessions, prefilling sets
      plan.py           program weeks, ramp-in sets, duration estimates
    cli.py              import / seed-if-empty / backup
  alembic/              migrations
  tests/
frontend/
  src/
    pages/              Today, Workout, Plan, Exercises, History, Stats, Settings
    components/         ExerciseTracker, SetRow, Stepper, RestTimerBar, ExercisePicker, ui/
    lib/saveQueue.ts    offline-safe autosave queue
seed/                   your library CSV + plan ZIP
data/                   database, images, backups (created at runtime)
```
