# Step 9 — Split the biweekly universe job out of the engine onto GitHub Actions cron

**Goal:** pick a cloud-hosting shape that prioritizes cost, and resolve a
scheduling conflict it exposed. The engine only needs to be up during **market
hours**, but the `buy_universe` rebuild must run **biweekly, preferably on a
weekend** — and that job lived on an in-process scheduler thread, so a
market-hours-only engine would never be alive on a Saturday to fire it. Fix:
hoist the job out of the engine into an external scheduler (GitHub Actions cron),
where the cadence + day-of-week live in the cron expression, not in code. This is
free and gets the heavy, infrequent job off the live trading process.

## Hosting decision (context for the split)

- The engine has **no inbound traffic** — it makes outbound connections to Alpaca
  + Supabase. No load balancer / public IP ingress / PaaS web tier needed.
- State is external (Supabase), so the host is **disposable**; restarts are
  replay-safe (`client_order_id` dedupe + `job_runs` resume).
- **Cost reality:** on a flat-rate VM, stopping it outside market hours saves
  **nothing** (you pay unless you delete it). So "market hours only" is an
  operational nicety, not a cost lever — leave a tiny VM up 24/7 and let the
  engine idle off-hours. Per-second billing (AWS/GCP) is the only way uptime
  scheduling cuts cost, and the orchestration isn't worth ~$1/mo.
- **Plan:** engine → one cheap always-on flat VM (**Hetzner CAX11 ≈ €3.79/mo**,
  or **Oracle ARM Always Free** for $0 with reclamation risk) via the existing
  systemd unit. Job → free GH Actions cron. **This step does the job split;
  Hetzner is the next step.**

## Files touched

| File                              | Change                                                                                                                  |
| --------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `run_job.py`                      | **New.** Standalone single-job runner: `python run_job.py <name>`. Records `job_runs`, Discord-alerts + exits non-zero on failure |
| `engine.py`                       | **Removed the in-process job scheduler** — `_start_scheduler`, `_job_scheduler`, `_check_jobs`, `_job_due`, `_run_job`, the `_scheduler_*` state, `start()`/`shutdown()` wiring, and the now-unused `JOB_REGISTRY` / `timedelta` imports. Watchdog untouched |
| `config/service_settings.py`      | Dropped `JOB_SCHEDULER_INTERVAL_SECONDS` and `run_on_boot_if_stale` (dead). Kept `JOBS` as cadence documentation; cron is now source of truth |
| `jobs/buy_universe.py`            | Retired the divergent `__main__` block so `run_job.py` is the one canonical run path                                   |
| `.github/workflows/buy-universe.yml` | **New.** Saturday 14:00 UTC cron + `workflow_dispatch`, biweekly via ISO-week-parity gate, concurrency-guarded         |

## What changed

### run_job.py — the external entrypoint

A generic dispatcher mirroring the engine's old `_run_job` contract so the audit
+ alerting behavior is unchanged, just driven from outside the process:

- Builds a **minimal context** (db + Alpaca data/trader, **no gateway** — jobs
  never place risk-checked orders).
- Looks the job up in `JOB_REGISTRY` by name; unknown name → exit `2`.
- On success: `record_job_run(name, "ok", detail)`, exit `0`.
- On failure: logs the traceback, **pages Discord** (`@here biweekly <name> job
  failed`), `record_job_run(name, "failed", str(e))`, exit `1` — so the external
  scheduler also marks the run red.

### engine.py — scheduler removed from the daemon threads

The whole periodic-job machinery is gone; the engine now owns only strategies +
the watchdog. `start()` no longer calls `_start_scheduler()`; `shutdown()` no
longer sets/joins a scheduler thread. `_parse_ts` stays (watchdog still parses
heartbeat timestamps). Verified no dangling references to any removed symbol.

### GitHub Actions workflow — biweekly weekend cron

- `cron: "0 14 * * 6"` → every **Saturday 14:00 UTC**, plus a
  `workflow_dispatch` button for manual smoke-tests.
- **GH cron can't express "every other week,"** so a gate step skips **odd ISO
  weeks** (`$((10#$(date -u +%V) % 2))`) → effectively biweekly. Manual runs
  always proceed. Flip the parity to shift which Saturdays run.
- `concurrency` group prevents a manual run from overlapping a scheduled one.
- Secrets/vars injected via the step `env:` block (see below).

### Secrets: GH Actions ↔ `os.getenv` — confirmed compatible, no code change

GH Actions sets each secret/variable as a real **process env var** via the step
`env:` block, which is exactly what `ServiceSettings`' `os.getenv(...)` reads at
import time. Local vs CI differ only in how env gets populated: local uses
`.env` + `load_dotenv()`; on the runner there's no `.env` (gitignored) so
`load_dotenv()` is a harmless no-op and `os.getenv` reads the runner-injected
vars. `load_dotenv` defaults to `override=False`, so it never clobbers real env
vars. Names must match exactly. `ALPACA_PAPER` arrives as a string, so the
existing `.lower() == "true"` comparison behaves identically.

## Verifying

- **Syntax + imports:** all touched files parse; `run_job` and `engine` import
  cleanly with no network; `run_job.JOB_REGISTRY` lists `buy_universe`.
- **No dangling refs:** grep confirms `engine.py` has no scheduler/`JOB_REGISTRY`
  leftovers, and nothing references the removed settings.
- **First real run (TODO, on GitHub):** add the secrets, push the branch, then
  **Actions → buy_universe → Run workflow** (bypasses the biweekly gate). Confirm
  it rebuilds the `universe` table and writes a `job_runs` row.

## Notes for later steps / TODO

- **Add repo secrets** before the workflow can run: `ALPACA_API_KEY`,
  `ALPACA_SECRET_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`, `DISCORD_WEBHOOK_URL`
  (+ optional variable `ALPACA_PAPER`, defaults `true`).
- **Confirm biweekly phase:** the gate runs on **even** ISO weeks. If the
  intended Saturdays are odd weeks, flip the comparison.
- **Next step — Hetzner:** provision the always-on engine VM (systemd unit in
  `deploy/`), drop in `.env`, enable the service. Job is already off the box.
- Still open from Step 8: no request timeout on `StockHistoricalDataClient` (a
  stalled batch can hang the now-unattended job — worth adding before relying on
  the cron); `MAX_DAILY_LOSS` still unenforced.
