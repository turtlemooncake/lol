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

    ALPHAVANTAGE_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "")

    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

    DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

    # ---------------------------------------------------------------------------
    # Data Settings
    # ---------------------------------------------------------------------------
    CANDLE_HISTORY_DAYS = 365  # Download 12 months of daily bars
    ALPACA_BAR_BATCH_SIZE = 20  # Symbols per multi-bar request
    TOP_X_STOCKS = 135
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
    JOBS = {
        "buy_universe": {
            "interval_days": 14,  # your biweekly universe rebuild
            "run_on_boot_if_stale": True,  # run immediately if overdue at startup
        },
    }

    # ---------------------------------------------------------------------------
    # Admin API (the "side door")
    # ---------------------------------------------------------------------------
    ADMIN_API_ENABLED = True
    ADMIN_API_HOST = "127.0.0.1"
    ADMIN_API_PORT = 8765

    # ---------------------------------------------------------------------------
    # Watchdog
    # ---------------------------------------------------------------------------
    HEARTBEAT_STALE_SECONDS = 600  # strategy considered wedged after this

    # ---------------------------------------------------------------------------
    # Risk (enforced by OrderGateway, global across all strategies)
    # ---------------------------------------------------------------------------
    MAX_ORDER_NOTIONAL = 100  # hard cap on any single order, $
    MAX_DAILY_LOSS = 100  # engine pauses itself past this, $

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
                "poll_interval": 5,  # revert back to 300s later
                "lookback_bars": 20,
                "universe": "buy",  # filled by build_universe job
            },
        },
    }
