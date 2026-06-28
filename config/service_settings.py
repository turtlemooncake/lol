import os
from dotenv import load_dotenv

load_dotenv()


class ServiceSettings:
    # ---------------------------------------------------------------------------
    # API Keys
    # ---------------------------------------------------------------------------
    ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
    ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
    ALPACA_PAPER = os.getenv("ALPACA_PAPER", "true").lower() == "true"

    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

    DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

    # ---------------------------------------------------------------------------
    # Data Settings
    # ---------------------------------------------------------------------------
    CANDLE_HISTORY_DAYS = 365  # Download 12 months of daily bars
    ALPACA_BAR_BATCH_SIZE = 20  # Symbols per multi-bar request
    TOP_X_STOCKS = 150
    MIN_STOCK_PRICE = 15.0
    MIN_STOCK_TRADE_VOLUME = 8_000
    MIN_VOLUME_DAYS_PCT = 0.75

    # Substrings (case-insensitive) that mark an asset as a bond/fixed-income
    # fund. Matched against the asset name to drop them from the universe.
    BOND_FUND_NAME_KEYWORDS = (
        "bond",
        "treasury",
        "fixed income",
        "municipal",
        "muni ",
        "aggregate bond",
        "income fund",
        "t-bill",
        "tips",
        "fund",
    )

    # ---------------------------------------------------------------------------
    # DB Settings
    # ---------------------------------------------------------------------------
    UNIVERSE_TABLE_NAME = "universe"

    # ---------------------------------------------------------------------------
    # Periodic jobs
    # ---------------------------------------------------------------------------
    # The engine no longer runs jobs in-process; the cadence + day-of-week now
    # live in an external scheduler (GitHub Actions cron) that invokes
    # `python run_job.py <name>`. interval_days is kept as documentation of the
    # intended cadence, but the cron schedule is the source of truth.
    JOBS = {
        "buy_universe": {
            "interval_days": 14,  # biweekly universe rebuild (Saturday cron)
        },
    }

    # ---------------------------------------------------------------------------
    # Watchdog
    # ---------------------------------------------------------------------------
    HEARTBEAT_STALE_SECONDS = 600  # strategy considered wedged after this
    WATCHDOG_INTERVAL_SECONDS = 60  # how often the watchdog scans heartbeats

    # ---------------------------------------------------------------------------
    # Risk (enforced by OrderGateway, global across all strategies)
    # ---------------------------------------------------------------------------
    MAX_ORDER_NOTIONAL = 100  # hard cap on any single order, $
    MAX_DAILY_LOSS = 100  # engine pauses itself past this, $
    MAX_OPEN_ORDERS = 10  # gateway refuses to submit past this many open broker orders
    MIN_ACCOUNT_CASH = (
        100  # gateway halts new orders once account cash drops below this, $
    )

    # ---------------------------------------------------------------------------
    # Strategies
    # Each entry: enabled at boot, capital bucket ($ the gateway will let it
    # deploy), and strategy-specific params passed to its constructor.
    # ---------------------------------------------------------------------------
    STRATEGIES = {
        # todo: refine these parameters
        "rsi_buy": {
            "enabled": True,
            "capital": 1_000,
            "params": {
                "rsi_period": 14,
                "rsi_threshold": 30.0,
                "poll_interval": 300,  # revert back to 300s later
                "universe": "buy",  # filled by build_universe job
                "order_notional": 100.0,  # $ per oversold name (must be <= MAX_ORDER_NOTIONAL)
            },
        },
        # Watches open positions and closes them on a take-profit or time-stop.
        # capital 0: exits don't deploy capital, so the gateway bucket is moot.
        "exit_monitor": {
            "enabled": True,
            "capital": 0,
            "params": {
                "poll_interval": 300,  # review positions every 5 min
                "take_profit_pct": 0.03,  # close at +3% unrealized
                "max_hold_days": 10,  # or once held 10 calendar days
            },
        },
        # Throwaway tick-only strategy for verifying the threading model
        # (Step 1). Disable once interleaving + single-Ctrl-C are confirmed.
        "heartbeat": {
            "enabled": False,
            "capital": 0,
            "params": {
                "poll_interval": 3,
            },
        },
    }
