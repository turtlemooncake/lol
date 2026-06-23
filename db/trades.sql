-- trades: the audit log the OrderGateway writes to.
--
-- One row per OrderIntent the gateway processes. The row is inserted BEFORE the
-- broker call (status 'pending'), so a crash mid-submit still leaves a durable
-- record; client_order_id is unique, so a replay is idempotent at the broker.
-- Rejected intents are recorded too (status 'rejected'), for the audit trail.
--
-- status lifecycle: pending -> submitted | failed ; or rejected (never submitted)

create table if not exists trades (
    id               uuid primary key default gen_random_uuid(),
    client_order_id  text not null unique,        -- strategy__symbol__<rand>
    strategy         text not null,
    symbol           text not null,
    side             text not null,
    notional         numeric not null,            -- dollars
    status           text not null default 'pending',
    reason           text default '',             -- rejection / failure detail
    broker_order_id  text,                         -- Alpaca order id, once submitted
    created_at       timestamptz not null default now(),
    submitted_at     timestamptz
);

create index if not exists trades_strategy_idx   on trades (strategy);
create index if not exists trades_created_at_idx  on trades (created_at desc);
