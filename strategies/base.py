import logging
import time
import threading
from abc import ABC, abstractmethod

from config.context import Context

logger = logging.getLogger("strategy")


class Strategy(ABC):
    """Base class. Subclasses implement loop_once(); the base owns the loop."""

    name: str = "base"

    # Trading strategies should only act while the market is open. A test-only
    # strategy (e.g. Heartbeat) overrides this to False to keep ticking always.
    requires_market_open: bool = True

    def __init__(self, ctx: Context, params: dict):
        self.ctx = ctx
        self.params = params
        self.poll_interval = params.get("poll_interval", 300)
        self.error_backoff = 30
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def setup(self) -> None:
        """One-time prep before the loop. Optional override."""

    def teardown(self) -> None:
        """Cleanup on stop. Optional override."""

    def stop(self) -> None:
        self._stop.set()

    @abstractmethod
    def loop_once(self) -> None:
        """One iteration. Raise freely — run() catches and logs."""

    def run(self) -> None:
        log = logging.getLogger(f"strategy.{self.name}")
        log.info("starting (poll every %ds)", self.poll_interval)

        try:
            self.setup()
        except Exception:
            log.exception("setup failed - strategy no run")
            return

        # Beat once before the loop so a heartbeat row exists immediately. If the
        # very first loop_once wedges, the watchdog still has a row to age out.
        self.ctx.db.beat(self.name, status="starting")

        while not self._stop.is_set():
            # Market-open gate: when closed, skip loop_once but stay alive --
            # still beat (or the watchdog flags us wedged) and sleep until the
            # next check. No orders fire outside market hours.
            if self.requires_market_open and not self.ctx.alpacaTrader.is_market_open():
                self.ctx.db.beat(self.name, status="market_closed")
                self._stop.wait(self.poll_interval)
                continue
            try:
                self.loop_once()
            except Exception:
                log.exception("loop_once error - backing off %ds", self.error_backoff)
                self._stop.wait(self.error_backoff)
                continue
            # A completed loop_once is the proof of life the watchdog watches for.
            # A thread stuck *inside* loop_once never reaches here -> goes stale.
            self.ctx.db.beat(self.name, status="running")
            self._stop.wait(self.poll_interval)

        # Clean stop: run teardown for flush/cleanup, then mark the heartbeat
        # 'stopped' so the health view reads a deliberate exit, not a wedge.
        # teardown is wrapped so its failure can't skip the final beat/log.
        try:
            self.teardown()
        except Exception:
            log.exception("teardown failed")
        finally:
            self.ctx.db.beat(self.name, status="stopped")
            log.info("stopped")
