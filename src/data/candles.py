from datetime import datetime, timedelta
import time
from zoneinfo import ZoneInfo
from alpaca.data import DataFeed, TimeFrame
from alpaca.data.requests import StockBarsRequest

from alpaca.trading import Asset

from config.settings import ALPACA_BAR_BATCH_SIZE, CANDLE_HISTORY_DAYS
from src.clients.alpaca_client import DATA_CLIENT


class AssetCandles(Asset):
    pass


def download_candle_bars(assets: list[Asset]) -> list[dict]:
    # 365 days ago -to- (Now)
    now = datetime.now(ZoneInfo("America/New_York")) - timedelta(days=1)
    start = now - timedelta(
        days=CANDLE_HISTORY_DAYS
    )  # leave 1 day buffer from today for free tier

    total_batches = (len(assets) + ALPACA_BAR_BATCH_SIZE - 1) // ALPACA_BAR_BATCH_SIZE

    for i in range(0, len(assets), ALPACA_BAR_BATCH_SIZE):
        batch = assets[i : i + ALPACA_BAR_BATCH_SIZE]
        batch_num = i // ALPACA_BAR_BATCH_SIZE + 1

        try:
            request = StockBarsRequest(
                symbol_or_symbols=batch,
                timeframe=TimeFrame.Day,
                start=start,
                end=now,
                limit=None,
                feed=DataFeed.IEX,
            )

            bars = DATA_CLIENT.get_stock_bars(request)

            # Flatten the data

        except Exception as e:
            print(f"Error at get_stock_bars. Batch {batch_num}/{total_batches}: {e}")

        if batch_num % 10 == 0 or batch_num == total_batches:
            print(f"Batch {batch_num}/{total_batches} done")

        # Free tier limit: 200 req/min, ~3 req/sec
        time.sleep(0.4)
