import sys
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from src.data.assets import get_all_filtered_assets
from src.data.candles import download_candle_bars
from src.util.analysis import returns_analysis


def main():
    start_time = time.time()

    # 1. Pull all assets and filter
    # assets = get_all_filtered_assets()
    # assets = [asset.symbol for asset in assets]
    assets = ["RACE"]

    # 2. Download Daily Bars
    candles_df = download_candle_bars(assets)

    # 3. Price analysis
    analysis_df = returns_analysis(candles_df)

    print(analysis_df)


if __name__ == "__main__":
    print("universe builder")
    main()
