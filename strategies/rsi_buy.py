import logging

import pandas as pd

from config.service_settings import ServiceSettings
from strategies.base import Strategy

log = logging.getLogger("strategy.rsi_buy")


class RsiBuy(Strategy):
    name = "rsi_buy"

    def setup(self) -> None:
        self.rsi_period = self.params.get("rsi_period", 14)
        self.rsi_threshold = self.params.get("rsi_threshold", 30.0)

    def loop_once(self) -> None:
        # 1. Universe, already ordered by weighted_score descending.
        rows = self.ctx.db.fetch_rows(ServiceSettings.UNIVERSE_TABLE_NAME)
        symbols = [r["symbol"] for r in rows]
        if not symbols:
            log.warning("universe empty - nothing to score")
            return

        # 2. Daily bars -> latest 14-period RSI per symbol.
        candles = self.ctx.alpacaData.download_candle_bars(symbols)
        if candles.empty:
            log.warning("no candle data returned for %d symbols", len(symbols))
            return

        rsi_by_symbol = self._latest_rsi(candles)

        log.info(rsi_by_symbol)

        # 3. Oversold = RSI <= threshold, keeping the weighted_score order.
        oversold = [
            (s, rsi_by_symbol[s])
            for s in symbols
            if s in rsi_by_symbol and rsi_by_symbol[s] <= self.rsi_threshold
        ]
        self.oversold = oversold  # Step 3 turns these into OrderIntents

        log.info(
            "scored %d symbols, %d oversold (RSI <= %g): %s",
            len(rsi_by_symbol),
            len(oversold),
            self.rsi_threshold,
            ", ".join(f"{s}={v:.1f}" for s, v in oversold) or "none",
        )

    def _latest_rsi(self, candles: pd.DataFrame) -> dict[str, float]:
        """Wilder's RSI; returns the most recent value per symbol."""
        period = self.rsi_period
        # Ensure each symbol's closes are in chronological order before diff().
        closes = candles.sort_index()["close"]

        def rsi(close: pd.Series) -> float:
            delta = close.diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            avg_gain = gain.ewm(
                alpha=1 / period, min_periods=period, adjust=False
            ).mean()
            avg_loss = loss.ewm(
                alpha=1 / period, min_periods=period, adjust=False
            ).mean()
            rs = avg_gain / avg_loss
            return (100 - 100 / (1 + rs)).iloc[-1]

        return closes.groupby(level="symbol").apply(rsi).dropna().to_dict()
