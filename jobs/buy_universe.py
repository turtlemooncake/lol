from config.context import Context
from config.service_settings import ServiceSettings
from util.db import convert_df_to_universe_rows
from util.universe_analysis import filter_penny_stocks, rank_stocks, returns_analysis


def build_universe(ctx: Context) -> str:
    """Rebuild the universe table from a fresh ranking.

    Uses the shared services off `ctx` (so the engine can run it on its
    scheduler thread without spinning up new clients). Returns a one-line detail
    string for the job_runs log; raises on failure so the scheduler records the
    run as 'failed' rather than a silent 'ok'.
    """
    # 1. Pull all assets and filter
    assets = ctx.alpacaTrader.get_all_filtered_assets()
    assets = [asset.symbol for asset in assets]

    # 2. Download Daily Bars
    raw_candles_df = ctx.alpacaData.download_candle_bars(assets)

    # 3. Filter out penny stocks
    candles_df = filter_penny_stocks(raw_candles_df)

    # 4. Price analysis
    analysis_df = returns_analysis(candles_df)

    # 5. Rank stock
    ranked_stocks_df = rank_stocks(analysis_df)

    # 6. Slice only top X stocks
    top_stocks_df = ranked_stocks_df.head(ServiceSettings.TOP_X_STOCKS)

    # 7. Clear previous table
    ctx.db.clear_table(ServiceSettings.UNIVERSE_TABLE_NAME)

    # 8. Convert to rows and upload to table
    top_stocks_db_rows = convert_df_to_universe_rows(top_stocks_df)
    rows_inserted = ctx.db.upsert_rows(
        ServiceSettings.UNIVERSE_TABLE_NAME, top_stocks_db_rows
    )
    return f"updated {rows_inserted} rows in {ServiceSettings.UNIVERSE_TABLE_NAME}"


if __name__ == "__main__":
    # Standalone path: build a minimal context (no gateway needed) and run once.
    from services.alpaca_data import AlpacaData
    from services.alpaca_trader import AlpacaTrader
    from services.supabase import SupabaseDB

    print("buy universe job")
    ctx = Context(
        db=SupabaseDB(),
        alpacaData=AlpacaData(),
        alpacaTrader=AlpacaTrader(),
    )
    print(build_universe(ctx))
    print("Fini with buy_universe.py!")
