import logging

import pandas as pd
import yfinance as yf

from config.service_settings import ServiceSettings
from strategies.base import Strategy

log = logging.getLogger("strategy.rsi_buy")


class RsiBuy(Strategy):
    name = "rsi_buy"

    def setup(self) -> None:
        self.rsi_period = self.params.get("rsi_period", 14)
        self.rsi_threshold = self.params.get("rsi_threshold", 30.0)
        self.vix_symbol = self.params.get("vix_symbol", "^VIX")
        self.vix_fallback_symbol = self.params.get("vix_fallback_symbol", "VIXY")
        self.vix_percentile = self.params.get("vix_percentile", 0.70)
        self.vix_lookback = self.params.get("vix_lookback", 252)  # ~1yr of bars

    def loop_once(self) -> None:
        # 1. Universe, already ordered by weighted_score descending.
        rows = self.ctx.db.fetch_rows(ServiceSettings.UNIVERSE_TABLE_NAME)
        symbols = [r["symbol"] for r in rows]
        if not symbols:
            log.warning("universe empty - nothing to score")
            return

        # 2. Volatility regime gate. If VIX is elevated, sit out entirely.
        if not self._vix_gate_open():
            self.oversold = []
            return

        # 3. Daily bars -> latest 14-period RSI per symbol.
        candles = self.ctx.alpacaData.download_candle_bars(symbols)
        if candles.empty:
            log.warning("no candle data returned for %d symbols", len(symbols))
            return

        rsi_by_symbol = self._latest_rsi(candles)

        # 4. Oversold = RSI <= threshold, keeping the weighted_score order.
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

    def _vix_gate_open(self) -> bool:
        """Volatility regime filter.

        Pulls a daily VIX close series (spot ^VIX, falling back to the VIXY
        proxy) and asks whether the latest reading sits in the lower
        `vix_percentile` of its trailing `vix_lookback` window. Fail-closed:
        if no source yields usable data, no entries are allowed.
        """
        closes = self._fetch_spot_vix()
        source = self.vix_symbol
        if closes is None:
            log.warning(
                "spot VIX (%s) unavailable - falling back to %s",
                self.vix_symbol,
                self.vix_fallback_symbol,
            )
            closes = self._fetch_vix_proxy()
            source = self.vix_fallback_symbol

        if closes is None:
            log.warning("no VIX data from any source - gate closed")
            return False

        return self._percentile_gate_open(closes, source)

    def _fetch_spot_vix(self) -> pd.Series | None:
        """Daily spot VIX closes from yfinance. None on any failure."""
        try:
            df = yf.download(
                self.vix_symbol,
                period="2y",
                interval="1d",
                auto_adjust=False,
                progress=False,
            )
            if df is None or df.empty:
                return None
            closes = df["Close"]
            # A single-ticker download can still return a 1-col frame.
            if isinstance(closes, pd.DataFrame):
                closes = closes.iloc[:, 0]
            closes = closes.dropna()
            return closes if not closes.empty else None
        except Exception:
            log.exception("yfinance VIX fetch failed")
            return None

    def _fetch_vix_proxy(self) -> pd.Series | None:
        """Daily VIXY-proxy closes via Alpaca. None when no data returned."""
        candles = self.ctx.alpacaData.download_candle_bars([self.vix_fallback_symbol])
        if candles.empty:
            return None
        closes = candles.sort_index()["close"]
        if isinstance(closes.index, pd.MultiIndex):
            closes = closes.xs(self.vix_fallback_symbol, level="symbol")
        closes = closes.dropna()
        return closes if not closes.empty else None

    def _percentile_gate_open(self, closes: pd.Series, source: str) -> bool:
        """True iff the latest close is in the lower `vix_percentile` of the
        trailing `vix_lookback` window. Fail-closed on short history."""
        window = closes.iloc[-self.vix_lookback :]
        if len(window) < self.vix_lookback:
            log.warning(
                "VIX history too short (%s: %d/%d bars) - gate closed",
                source,
                len(window),
                self.vix_lookback,
            )
            return False

        threshold = window.quantile(self.vix_percentile)
        latest = window.iloc[-1]
        is_open = latest <= threshold
        log.info(
            "VIX gate %s via %s: latest=%.2f, %dth pct(%dd)=%.2f",
            "open" if is_open else "closed",
            source,
            latest,
            int(self.vix_percentile * 100),
            self.vix_lookback,
            threshold,
        )
        return is_open

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
