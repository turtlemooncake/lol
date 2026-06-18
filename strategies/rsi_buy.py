import logging

from strategies.base import Strategy

log = logging.getLogger("strategy.rsi_buy")


class RsiBuy(Strategy):
    name = "rsi_buy"

    def loop_once(self) -> None:
        log.info("tick")  # Step 3 will turn this into an OrderIntent
