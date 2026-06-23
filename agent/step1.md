# Step 1 — Run all enabled strategies concurrently

**Goal:** every enabled entry in `STRATEGIES` runs on its own daemon thread, and a
single Ctrl-C joins all of them.

This generalizes the Step 0 scaffolding (one hard-coded strategy) into a loop over
config. `main.py` stays trivially readable — orchestration moves into an `Engine` in
Step 2.

## Files touched

| File | Change |
|------|--------|
| `main.py` | Loop over `STRATEGIES`, start each enabled strategy on a daemon thread, one shutdown handler joins all |
| `strategies/heartbeat.py` | Throwaway tick-only strategy, exists only to verify the threading model |
| `strategies/__init__.py` | Register `Heartbeat` in `REGISTRY` |
| `config/service_settings.py` | Add an enabled `heartbeat` entry (`poll_interval: 3`) |

## What changed

### `main.py`
- Replaced the hard-coded `rsi_buy` block with a loop over `ServiceSettings.STRATEGIES`:
  - skip entries where `enabled` is falsy (logged),
  - skip names missing from `REGISTRY` (logged warning),
  - otherwise instantiate `cls(ctx, cfg["params"])` and start it on
    `threading.Thread(target=strat.run, name=f"strat-{name}", daemon=True)`.
- Collects `(strat, thread)` pairs; bails early with a warning if nothing is enabled.
- **One** `SIGINT`/`SIGTERM` handler sets a shared `shutdown` Event; the main thread
  blocks on it. On shutdown: `stop()` **all** strategies first, then `join(timeout=10)`
  each — so a single Ctrl-C signals every strategy before any join blocks.

### `strategies/heartbeat.py`
- `Heartbeat(Strategy)` with `name = "heartbeat"` and a `loop_once()` that logs `tick`.
- No `ctx` use, no orders — pure scaffolding to prove two streams interleave.

### `strategies/__init__.py`
- `REGISTRY` now maps both `rsi_buy` and `heartbeat`.

### `config/service_settings.py`
- Added an enabled `heartbeat` entry with `poll_interval: 3` (offset from `rsi_buy`'s
  5s so the two log streams visibly interleave).

## Verifying

```bash
python main.py
```

- Expected: `[strat-rsi_buy]` and `[strat-heartbeat]` log lines interleaving; a single
  Ctrl-C prints `shutting down...` then `stopped` for both within ~1s.
- `build_context()` still builds the real Supabase/Alpaca clients, and `rsi_buy`'s
  `loop_once()` hits the DB/Alpaca — so a full run needs `.env` keys. To eyeball only
  the threading model, disable `rsi_buy` and stub `ctx = None`; the heartbeat alone
  still exercises start/join/Ctrl-C.

## Notes for later steps

- `heartbeat` is throwaway. Disable it (or delete the entry + file) once interleaving
  and single-Ctrl-C are confirmed.
- **Step 2** moves this start/join orchestration out of `main.py` into an `Engine`.
  Keep `main.py` thin here.
