from dateutil.relativedelta import relativedelta
import numpy as np
from pandas import DataFrame
import pandas as pd

from config.service_settings import ServiceSettings


def filter_penny_stocks(
    df: DataFrame,
    min_price=ServiceSettings.MIN_STOCK_PRICE,
    min_avg_volume=ServiceSettings.MIN_STOCK_TRADE_VOLUME,
    min_days_pct=ServiceSettings.MIN_VOLUME_DAYS_PCT,
):
    by_symbol = df.groupby("symbol")

    median_price = by_symbol["close"].median()
    median_volume = by_symbol["volume"].median()
    current_price = by_symbol["close"].last()  # latest close price

    # What % of trading days met the volume threshold
    days_above = by_symbol["volume"].apply(lambda v: (v >= min_avg_volume).mean())

    """
    DEBUG know how of df types
    
    symbol = "RACE"
    print(f"median_price: {median_price.loc[symbol]}")
    print(f"median_volume: {median_volume.loc[symbol]}")
    print(f"current_price: {current_price.loc[symbol]}")
    print(f"days_above: {days_above.loc[symbol]}")
    """

    valid = median_price[
        (median_price >= min_price)
        & (median_volume >= min_avg_volume)
        & (days_above >= min_days_pct)
        & (current_price >= min_price)
    ].index

    return df[df.index.get_level_values("symbol").isin(valid)]


def returns_analysis(df: DataFrame):
    """
    Simple return, Sharpe ratio, Sortino ratio
    """
    # Guard
    if df.empty:
        return pd.DataFrame()

    latest_date = df.index.get_level_values("timestamp").max()

    periods = {
        "3m": latest_date - relativedelta(months=3),
        "6m": latest_date - relativedelta(months=6),
        "12m": latest_date - relativedelta(months=12),
    }

    latest_close = df.groupby("symbol")["close"].last()

    results = {"close": latest_close}

    for period, cutoff_date in periods.items():
        period_df = df.loc[df.index.get_level_values("timestamp") >= cutoff_date]

        # Simple return
        past_close = period_df.groupby("symbol")["close"].first()
        results[f"return_{period}"] = (latest_close - past_close) / past_close

        # Ratio returns
        # we use pct to standardize the amt of change between prices
        # so that $1000 change and $10 change are appropriately measured
        daily_returns_pct = period_df.groupby("symbol")["close"].pct_change()
        mean = daily_returns_pct.groupby("symbol").mean()

        # Sortino ratio
        downside = daily_returns_pct.where(daily_returns_pct < 0)
        downside_std = downside.groupby("symbol").std()
        results[f"sortino_{period}"] = (mean / downside_std) * np.sqrt(252)

        # Sharpe ratio
        std = daily_returns_pct.groupby("symbol").std()
        results[f"sharpe_{period}"] = (mean / std) * np.sqrt(252)

    result_df = pd.DataFrame(results).dropna()

    weight_columns = [c for c in result_df.columns if c != "close"]
    weights = {
        "sortino_3m": 9,
        "sharpe_3m": 8,
        "return_3m": 7,
        "sortino_6m": 6,
        "sharpe_6m": 5,
        "return_6m": 4,
        "sortino_12m": 3,
        "sharpe_12m": 2,
        "return_12m": 1,
    }

    total_weight = sum(weights.values())
    result_df["weighted_score"] = (
        sum(result_df[col] * weights[col] for col in weight_columns) / total_weight
    )

    return result_df.sort_values("weighted_score", ascending=False)


def rank_stocks(df: DataFrame):
    return pd.DataFrame(df).sort_values(
        by=[
            "sortino_3m",
            "sharpe_3m",
            "return_3m",
            "sortino_6m",
            "sharpe_6m",
            "return_6m",
            "sortino_12m",
            "sharpe_12m",
            "return_12m",
        ],
        ascending=False,
    )
