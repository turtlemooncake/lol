import sys
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from config.settings import TOP_X_STOCKS
from src.data.assets import get_all_filtered_assets
from src.data.candles import download_candle_bars
from src.util.analysis import filter_penny_stocks, rank_stocks, returns_analysis


def main():
    start_time = time.time()

    # 1. Pull all assets and filter
    assets = get_all_filtered_assets()
    assets = [asset.symbol for asset in assets]
    # assets = ["RACE"]

    # 2. Download Daily Bars
    candles_df = download_candle_bars(assets)

    # 3. Filter out penny stocks
    candles_df = filter_penny_stocks(candles_df)

    if candles_df.empty:
        print(f"No stocks passed filtering")
        return

    # 4. Price analysis
    analysis_df = returns_analysis(candles_df)

    # 5. Rank stock
    ranked_stocks_df = rank_stocks(analysis_df)

    # 6. Slice only top 135 stocks
    top_stocks_df = ranked_stocks_df.head(TOP_X_STOCKS)

    print(top_stocks_df)

    # 7. Clear previous table

    # 8. Convert to rows and upload to table


if __name__ == "__main__":
    print("universe builder")
    main()
