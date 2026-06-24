# Step 5 — Job scheduler (universe rebuild without cron)

**Goal:** `buy_universe` runs on its `interval_days` schedule from inside the
supervised process — no external cron — and the schedule **survives restarts**.
State lives in a `job_runs` table, so a restart resumes the cadence instead of
re-firing every job.

## Files touched

| File | Change |
|------|--------|
| `sql/schema.sql` | New `job_runs` table (append-only run log = the scheduler's clock) |
| `services/supabase.py` | New `record_job_run()` + `last_job_run()` |
| `jobs/buy_universe.py` | `main()` → `build_universe(ctx)` returning a detail string; standalone path kept |
| `jobs/__init__.py` | New `JOB_REGISTRY` (name → callable), mirroring `strategies/REGISTRY` |
| `engine.py` | New `_job_scheduler` daemon thread + `_check_jobs`/`_job_due`/`_run_job`; stopped in `shutdown()` |
| `config/service_settings.py` | Added `JOB_SCHEDULER_INTERVAL_SECONDS` |

## What changed

### `sql/schema.sql`
- `job_runs`: append-only log, one row per run — `id`, `name`, `status`
  (`'ok'`/`'failed'`), `detail`, `ran_at` (timestamptz). Index on
  `(name, ran_at DESC)` for the scheduler's only read: the latest run per name.
  Older rows are history/audit.

### `services/supabase.py`
- `record_job_run(name, status, detail)` — inserts one row. Writes `ran_at`
  itself in UTC so the due-math compares two clocks on the **same machine**
  (never app-vs-DB skew), same discipline as `beat()`. **Fail-soft**: logs only.
- `last_job_run(name)` — most recent row for `name` (`None` if never run). Also
  returns `None` on a DB error, which the scheduler treats like "never run"
  (worst case: a transient error fires the job once early).

### `jobs/buy_universe.py`
- `main()` → **`build_universe(ctx)`**: pulls services off the shared `ctx`
  instead of constructing its own clients, so the engine can run it on the
  scheduler thread. Returns a one-line detail string (e.g. `"updated N rows in
  universe"`) for the `job_runs` log; **raises** on failure so the scheduler
  records `failed` rather than a silent `ok`.
- The `if __name__ == "__main__"` path is kept — it builds a minimal `Context`
  (no gateway needed) and runs once, so the job still works standalone.

### `jobs/__init__.py`
- `JOB_REGISTRY = {"buy_universe": build_universe}` — the scheduler looks jobs
  up here the same way `start_strategy` uses `strategies/REGISTRY`.

### `engine.py`
- `start()` launches `_start_scheduler()` after the watchdog.
- `_job_scheduler()` is a daemon thread that **scans once immediately** (so an
  overdue job fires at boot) then every `JOB_SCHEDULER_INTERVAL_SECONDS`. It
  loops on `self._scheduler_stop.wait(interval)`, which returns the instant
  shutdown sets the event — so even a day-long interval stops promptly.
  Deliberately **its own timer thread, not the strategy poll loop**: a heavy,
  infrequent job must not stall a strategy's tick.
- `_check_jobs()` walks `ServiceSettings.JOBS`, skips names with no
  `JOB_REGISTRY` entry, and runs any that are due.
- `_job_due(name, cfg, now)` — due if `last_job_run` is `None` **and**
  `run_on_boot_if_stale`, or its `ran_at` is older than `interval_days`. A run
  of any status (ok *or* failed) resets the clock, so a broken job backs off to
  the next interval instead of hammering on every scan.
- `_run_job(name, fn)` — runs the job inline on the scheduler thread and records
  `ok` (with the returned detail) or `failed` (with the exception text).
- `_parse_beat_at` was renamed `_parse_ts` (now parses `ran_at` too).
- `shutdown()` sets `_scheduler_stop` and joins the scheduler thread alongside
  the watchdog and strategy threads.

### `config/service_settings.py`
- Added `JOB_SCHEDULER_INTERVAL_SECONDS = 86400` (once a day). `interval_days`
  is the real cadence, so a daily scan is plenty fine-grained; shutdown still
  interrupts the wait immediately.

## Verifying

Run `sql/schema.sql` once in Supabase to create `job_runs`, then:

- **Fires on boot when stale**: with `job_runs` empty, start the engine.
  `buy_universe` is due (null last run + `run_on_boot_if_stale`), runs, and
  writes one `status='ok'` row with a detail string.
- **No longer due right after**: the next scan sees a fresh `ran_at` < 14 days
  old and skips it — nothing re-fires. (To watch it without a full day's wait,
  temporarily lower `JOB_SCHEDULER_INTERVAL_SECONDS`.)
- **Failure path**: make `build_universe` raise; the scheduler logs `job
  buy_universe failed` and writes a `status='failed'` row. The clock still
  advances, so it retries on the next interval, not the next scan.
- **Standalone still works**: `python -m jobs.buy_universe` runs the rebuild once
  via the kept `__main__` path.
- **Clean shutdown**: Ctrl-C — the scheduler stops and joins with the watchdog
  and strategies; no lingering thread.

## Notes for later steps

- The scheduler runs jobs **inline** on its one thread: jobs are serialized, and
  a job still in flight at shutdown is a daemon thread that dies with the process
  (the `join` timeout won't wait it out). Fine for one infrequent job; revisit if
  jobs multiply or get long.
- Adding a job is now: write `build_x(ctx) -> str`, register it in
  `JOB_REGISTRY`, add a `JOBS` config entry. No engine change.
- `job_runs` is the natural read for an admin API "last run / next due" view.
