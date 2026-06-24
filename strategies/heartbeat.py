import logging

from strategies.base import Strategy

log = logging.getLogger("strategy.heartbeat")


class Heartbeat(Strategy):
    """Throwaway strategy that just logs a tick each loop.

    Exists to verify the threading model (Step 1): enable it alongside
    rsi_buy and confirm two log streams interleave and a single Ctrl-C
    joins both. No orders, no ctx use.
    """

    name = "heartbeat"
    # Pure liveness probe, no orders -- tick regardless of market hours so it
    # stays useful for verifying the threading model overnight/weekends.
    requires_market_open = False

    def loop_once(self) -> None:
        log.info("tick")
