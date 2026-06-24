-- =========================================================================
-- universe: the current top 135 ranked stocks
-- =========================================================================
CREATE TABLE IF NOT EXISTS universe (
    symbol          TEXT NOT NULL,
    snapshot_date   DATE NOT NULL,
    weighted_score            REAL,
    return_3m       REAL,
    sortino_3m       REAL,
    sharpe_3m       REAL,
    return_6m       REAL,
    sortino_6m       REAL,
    sharpe_6m       REAL,
    return_12m       REAL,
    sortino_12m       REAL,
    sharpe_12m       REAL,
    PRIMARY KEY (symbol, snapshot_date)
);

-- =========================================================================
-- heartbeats: the liveness table the engine's watchdog reads.
--
-- One row per strategy (name is the key). The strategy upserts its row at the
-- end of every loop_once via ctx.db.beat(name, status), refreshing beat_at. A
-- thread that is alive but wedged (e.g. stuck in a blocking call) keeps its
-- thread.is_alive() True but stops beating -- which try/except can never catch.
-- The watchdog flags any beat_at older than HEARTBEAT_STALE_SECONDS.
-- =========================================================================
CREATE TABLE IF NOT EXISTS heartbeats (
    name      TEXT PRIMARY KEY,            -- strategy name
    status    TEXT NOT NULL DEFAULT 'running',
    beat_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =========================================================================
-- job_runs: append-only log of periodic job runs (the scheduler's clock).
--
-- The engine's _job_scheduler thread runs each entry in ServiceSettings.JOBS
-- on its interval_days schedule. A job is "due" when it has never run (and is
-- run_on_boot_if_stale) or its most recent ran_at is older than interval_days.
-- One row is appended per run with status 'ok' | 'failed' and a detail string,
-- so the table doubles as an audit log. The scheduler reads only the latest
-- ran_at per name to decide due-ness; older rows are history.
-- =========================================================================
CREATE TABLE IF NOT EXISTS job_runs (
    id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name      TEXT NOT NULL,               -- job name (key into ServiceSettings.JOBS)
    status    TEXT NOT NULL,               -- 'ok' | 'failed'
    detail    TEXT,                        -- one-line result or error message
    ran_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The scheduler's hot path: most recent run for a given job name.
CREATE INDEX IF NOT EXISTS job_runs_name_ran_at_idx ON job_runs (name, ran_at DESC);