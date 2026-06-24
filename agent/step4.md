# Step 4 — Heartbeats + watchdog (catch the silent failure)

**Goal:** detect a thread that's *alive but wedged* — stuck in a blocking call or
deadlocked. The `try/except` in `base.run()` only catches a loop that **raises**;
a loop that **hangs** never returns, never raises, and `thread.is_alive()` stays
`True`. Nothing existing can see that. The watchdog can.

## Files touched

| File | Change |
|------|--------|
| `sql/schema.sql` | New `heartbeats` table (liveness log the watchdog reads) |
| `services/supabase.py` | New `beat()` (upsert one row per strategy) + `fetch_heartbeats()` |
| `strategies/base.py` | `run()` beats once before the loop and after every `loop_once()` |
| `engine.py` | New `_watchdog` daemon thread + `_check_heartbeats()`; stopped in `shutdown()` |
| `config/service_settings.py` | Added `WATCHDOG_INTERVAL_SECONDS` (`HEARTBEAT_STALE_SECONDS` already existed) |

## What changed

### `sql/schema.sql`
- `heartbeats` table: `name` (primary key — one row per strategy), `status`,
  `beat_at` (timestamptz). The strategy upserts its row each loop; the watchdog
  ages out `beat_at`.

### `services/supabase.py`
- `beat(name, status="running")` — upserts `{name, status, beat_at=now()}` on
  conflict `name`. **Fail-soft**: a DB hiccup only prints; it must never take
  down a strategy's loop.
- `fetch_heartbeats()` — returns all rows for the watchdog (`[]` on failure).
- The app writes `beat_at` itself (UTC) and the watchdog compares against its own
  UTC clock — same machine, so no app↔DB clock skew in the staleness math.

### `strategies/base.py`
- `run()` beats `status="starting"` **once before** the loop, so a heartbeat row
  exists immediately — if the *very first* `loop_once()` wedges, the watchdog
  still has a row to age out (otherwise there'd be no row to flag).
- After each successful `loop_once()`, beats `status="running"`. A completed
  `loop_once()` is the proof of life; a thread stuck *inside* `loop_once()` never
  reaches the beat → `beat_at` goes stale.

### `engine.py`
- `start()` launches `_start_watchdog()` after the strategies.
- `_watchdog()` is a daemon thread that, every `WATCHDOG_INTERVAL_SECONDS`, runs
  `_check_heartbeats()` (wrapped in try/except so a scan error can't kill it).
  It loops on `self._watchdog_stop.wait(interval)` — `wait()` returns `True` only
  when stopped, so the loop ticks on timeout and exits promptly on shutdown.
- `_check_heartbeats()` only inspects threads where `thread.is_alive()` — a *dead*
  thread is a different fault (visible via `status()`), and filtering to live
  threads also avoids flagging stale rows left by stopped/old strategies. For each
  live thread with no row it warns "alive but no heartbeat yet"; with a row older
  than `HEARTBEAT_STALE_SECONDS` it warns `WEDGED ... heartbeat <n>s old`.
- `_parse_beat_at()` parses the Supabase timestamptz (ISO-8601, tolerates a
  trailing `Z`) into an aware UTC datetime.
- `shutdown()` sets `_watchdog_stop` and joins the watchdog thread alongside the
  strategy threads.

### `config/service_settings.py`
- Added `WATCHDOG_INTERVAL_SECONDS = 60`. `HEARTBEAT_STALE_SECONDS = 600` was
  already present from an earlier step.

## Verifying

Run `sql/schema.sql` once in Supabase to create the `heartbeats` table, then:

- **Healthy path**: start the engine; each strategy writes a `heartbeats` row that
  refreshes every `poll_interval`. The watchdog logs nothing (warnings only).
- **Wedged path**: put `time.sleep(9999)` inside one strategy's `loop_once()`. Its
  `beat_at` freezes while the others keep refreshing. Within
  `HEARTBEAT_STALE_SECONDS` the watchdog logs `strategy <name> WEDGED: heartbeat
  <n>s old`, and the other strategies stay quiet (healthy).
  - To see it fast, temporarily lower `HEARTBEAT_STALE_SECONDS` (and/or
    `WATCHDOG_INTERVAL_SECONDS`) in settings.
- **Clean shutdown**: Ctrl-C — the watchdog stops and joins with the strategies;
  no lingering thread.

## Notes for later steps

- The watchdog currently **observes** (logs). A later step can make it **act** —
  page/alert (Discord webhook is already in settings), restart the wedged
  strategy, or trip the engine-level pause.
- `_check_heartbeats()` is also the natural read for the admin API's health view.
- A tight `poll_interval` relative to `HEARTBEAT_STALE_SECONDS` matters: stale must
  be comfortably larger than a strategy's slowest legitimate loop, or healthy
  strategies will false-positive.
