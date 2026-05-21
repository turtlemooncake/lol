import os
from dotenv import load_dotenv

load_dotenv()

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

# ---------------------------------------------------------------------------
# Data Settings
# ---------------------------------------------------------------------------
UNIVERSE_TABLE_NAME = "universe"
