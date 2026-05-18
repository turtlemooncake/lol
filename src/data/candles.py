from datetime import datetime, timedelta
import time
from zoneinfo import ZoneInfo
from alpaca.data import DataFeed, TimeFrame
from alpaca.data.requests import StockBarsRequest
import pandas as pd

pd.set_option("display.max_rows", None)
pd.set_option("display.max_columns", None)

from config.settings import ALPACA_BAR_BATCH_SIZE, CANDLE_HISTORY_DAYS
from src.clients.alpaca_client import DATA_CLIENT


def download_candle_bars(assets: list[str]) -> pd.DataFrame:
    now = datetime.now(ZoneInfo("America/New_York")) - timedelta(days=1)
    start = now - timedelta(days=CANDLE_HISTORY_DAYS)

    total_batches = (len(assets) + ALPACA_BAR_BATCH_SIZE - 1) // ALPACA_BAR_BATCH_SIZE
    symbol_candles = []

    for i in range(0, len(assets), ALPACA_BAR_BATCH_SIZE):
        batch = assets[i : i + ALPACA_BAR_BATCH_SIZE]
        batch_num = i // ALPACA_BAR_BATCH_SIZE + 1

        page_token = None

        while True:
            try:
                request = StockBarsRequest(
                    symbol_or_symbols=batch,
                    timeframe=TimeFrame.Day,
                    start=start,
                    end=now,
                    limit=None,
                    feed=DataFeed.IEX,
                    page_token=page_token,
                    adjustment="all",  # adjust for stock split, cash dividends, split offs
                )

                bars = DATA_CLIENT.get_stock_bars(request)

                symbol_candles.append(bars.df)

                page_token = None  # NOTE: did not find page token field in the python sdk response
                if not page_token:
                    break

                time.sleep(0.4)

            except Exception as e:
                print(
                    f"Error at get_stock_bars. Batch {batch_num}/{total_batches}: {e}"
                )
                break

        if batch_num % 10 == 0 or batch_num == total_batches:
            print(f"Batch {batch_num}/{total_batches} done")

        time.sleep(0.4)

    return pd.concat(symbol_candles) if symbol_candles else pd.DataFrame()
