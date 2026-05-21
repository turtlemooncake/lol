import sys
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from config.settings import TOP_X_STOCKS, UNIVERSE_TABLE_NAME
from src.data.assets import get_all_filtered_assets
from src.data.candles import download_candle_bars
from src.db.db import clear_table, convert_df_to_universe_rows, upsert_rows
from src.util.analysis import filter_penny_stocks, rank_stocks, returns_analysis


def main():
    # 1. Pull all assets and filter
    assets = get_all_filtered_assets()
    assets = [asset.symbol for asset in assets]

    # 2. Download Daily Bars
    raw_candles_df = download_candle_bars(assets)

    # 3. Filter out penny stocks
    candles_df = filter_penny_stocks(raw_candles_df)

    if candles_df.empty:
        print(f"No stocks passed filtering")
        return

    # 4. Price analysis
    analysis_df = returns_analysis(candles_df)

    # 5. Rank stock
    ranked_stocks_df = rank_stocks(analysis_df)

    # 6. Slice only top 135 stocks
    top_stocks_df = ranked_stocks_df.head(TOP_X_STOCKS)

    # 7. Clear previous table
    clear_table(UNIVERSE_TABLE_NAME)

    # 8. Convert to rows and upload to table
    top_stocks_db_rows = convert_df_to_universe_rows(top_stocks_df)
    rows_inserted = upsert_rows(UNIVERSE_TABLE_NAME, top_stocks_db_rows)
    print(f"Updated {rows_inserted} rows in {UNIVERSE_TABLE_NAME}")

    # 9. Fini!
    print(f"Fini with build_universe.py!")


if __name__ == "__main__":
    print("universe builder")
    main()
