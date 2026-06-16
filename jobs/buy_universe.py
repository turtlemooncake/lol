from config.service_settings import ServiceSettings
from services.alpaca_data import AlpacaData
from services.alpaca_trader import AlpacaTrader
from services.supabase import SupabaseDB
from util.db import convert_df_to_universe_rows
from util.universe_analysis import filter_penny_stocks, rank_stocks, returns_analysis


def main():
    # 0. Initialize clients
    TRADING_CLIENT = AlpacaTrader()
    DATA_CLIENT = AlpacaData()
    DB_CLIENT = SupabaseDB()

    # 1. Pull all assets and filter
    assets = TRADING_CLIENT.get_all_filtered_assets()
    assets = [asset.symbol for asset in assets]

    # 2. Download Daily Bars
    raw_candles_df = DATA_CLIENT.download_candle_bars(assets)

    # 3. Filter out penny stocks
    candles_df = filter_penny_stocks(raw_candles_df)

    # 4. Price analysis
    analysis_df = returns_analysis(candles_df)

    # 5. Rank stock
    ranked_stocks_df = rank_stocks(analysis_df)

    # 6. Slice only top 135 stocks
    top_stocks_df = ranked_stocks_df.head(ServiceSettings.TOP_X_STOCKS)

    # 7. Clear previous table
    DB_CLIENT.clear_table(ServiceSettings.UNIVERSE_TABLE_NAME)

    # 8. Convert to rows and upload to table
    top_stocks_db_rows = convert_df_to_universe_rows(top_stocks_df)
    rows_inserted = DB_CLIENT.upsert_rows(
        ServiceSettings.UNIVERSE_TABLE_NAME, top_stocks_db_rows
    )
    print(f"Updated {rows_inserted} rows in {ServiceSettings.UNIVERSE_TABLE_NAME}")

    # 9. Fini!
    print(f"Fini with buy_universe.py!")


if __name__ == "__main__":
    print("buy universe job")
    main()
