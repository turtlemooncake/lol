-- =========================================================================
-- universe: the current top 135 ranked stocks
-- =========================================================================
CREATE TABLE IF NOT EXISTS universe (
    ticker          TEXT NOT NULL,
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
    PRIMARY KEY (ticker, snapshot_date)
);