from dateutil.relativedelta import relativedelta
import numpy as np
from pandas import DataFrame
import pandas as pd


def returns_analysis(df: DataFrame):
    """
    Simple return, Sharpe ratio, Sortino ratio
    """
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

    return pd.DataFrame(results)
