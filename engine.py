import logging
import threading
from datetime import datetime, timedelta, timezone

from config.context import Context
from config.service_settings import ServiceSettings
from jobs import JOB_REGISTRY
from services.discord import send_discord_message
from strategies import REGISTRY
from strategies.base import Strategy
from util import parse_ts as _parse_ts

logger = logging.getLogger("engine")


class Engine:
    """Owns strategy instances and their threads.

    Strategies can be started/stopped individually (start_strategy/stop_strategy)
    or all at once (start/shutdown). This is the seam the admin API plugs into.
    """

    def __init__(self, ctx: Context):
        self.ctx = ctx
        self.strategies: dict[str, Strategy] = {}
        self.threads: dict[str, threading.Thread] = {}
        self._watchdog_stop = threading.Event()
        self._watchdog_thread: threading.Thread | None = None
        self._scheduler_stop = threading.Event()
        self._scheduler_thread: threading.Thread | None = None
        # Names already paged for a current wedge. Keeps the watchdog from
        # re-alerting every scan; cleared when a strategy beats fresh again so a
        # later re-wedge pages anew.
        self._wedged_alerted: set[str] = set()

    def start(self) -> None:
        """Start every enabled strategy in config, then the watchdog + scheduler."""
        for name, cfg in ServiceSettings.STRATEGIES.items():
            if not cfg.get("enabled"):
                logger.info("strategy %s disabled - skipping", name)
                continue
            self.start_strategy(name)
        logger.info("started %d strategies", len(self.threads))
        self._start_watchdog()
        self._start_scheduler()

    def _start_watchdog(self) -> None:
        """Launch the watchdog daemon that scans heartbeats for wedged threads."""
        if self._watchdog_thread is not None and self._watchdog_thread.is_alive():
            return
        self._watchdog_stop.clear()
        self._watchdog_thread = threading.Thread(
            target=self._watchdog, name="watchdog", daemon=True
        )
        self._watchdog_thread.start()
        logger.info(
            "watchdog started (scan every %ds, stale after %ds)",
            ServiceSettings.WATCHDOG_INTERVAL_SECONDS,
            ServiceSettings.HEARTBEAT_STALE_SECONDS,
        )

    def _watchdog(self) -> None:
        """Every WATCHDOG_INTERVAL_SECONDS, flag any strategy that's alive but
        hasn't beat within HEARTBEAT_STALE_SECONDS.

        try/except catches a thread that *crashes*; it cannot catch one that's
        alive but wedged (stuck in a blocking call, deadlocked). That silent
        failure is exactly what this loop exists to surface.
        """
        # wait() returns True only when stopped, so the loop ticks on timeout.
        while not self._watchdog_stop.wait(ServiceSettings.WATCHDOG_INTERVAL_SECONDS):
            try:
                self._check_heartbeats()
            except Exception:
                logger.exception("watchdog scan failed")

    def _check_heartbeats(self) -> None:
        beats = {hb.get("name"): hb for hb in self.ctx.db.fetch_heartbeats()}
        now = datetime.now(timezone.utc)
        stale = ServiceSettings.HEARTBEAT_STALE_SECONDS

        # Only a *live* thread can be wedged. A dead thread is a different fault
        # (caught by status()); we don't want to flag old rows from stopped ones.
        for name, thread in self.threads.items():
            if not thread.is_alive():
                continue
            hb = beats.get(name)
            beat_at = _parse_ts(hb.get("beat_at")) if hb else None
            if beat_at is None:
                logger.warning("strategy %s alive but has no heartbeat yet", name)
                continue
            age = (now - beat_at).total_seconds()
            if age > stale:
                logger.warning(
                    "strategy %s WEDGED: heartbeat %.0fs old (> %ds), last status=%s",
                    name,
                    age,
                    stale,
                    hb.get("status"),
                )
                self._alert_wedged(name, age, hb.get("status"))
            else:
                logger.debug("strategy %s healthy (%.0fs since beat)", name, age)
                # Recovered (or never wedged): re-arm so a future wedge pages.
                self._wedged_alerted.discard(name)

    def _alert_wedged(self, name: str, age: float, status) -> None:
        """Page Discord once per wedge. send_discord_message is fail-soft, so a
        webhook hiccup can't take down the watchdog scan."""
        if name in self._wedged_alerted:
            return  # already paged for this wedge; don't spam every scan
        self._wedged_alerted.add(name)
        send_discord_message(
            f"🚨 **Strategy wedged** — `{name}` heartbeat {age:.0f}s old "
            f"(> {ServiceSettings.HEARTBEAT_STALE_SECONDS}s), "
            f"last status `{status}`. Thread alive but not progressing."
        )

    def _start_scheduler(self) -> None:
        """Launch the job scheduler daemon that runs periodic jobs on schedule."""
        if self._scheduler_thread is not None and self._scheduler_thread.is_alive():
            return
        self._scheduler_stop.clear()
        self._scheduler_thread = threading.Thread(
            target=self._job_scheduler, name="scheduler", daemon=True
        )
        self._scheduler_thread.start()
        logger.info(
            "job scheduler started (scan every %ds)",
            ServiceSettings.JOB_SCHEDULER_INTERVAL_SECONDS,
        )

    def _job_scheduler(self) -> None:
        """Run each configured job on its interval_days cadence, restart-safe.

        Deliberately its own timer thread, not the strategy poll loop: a job
        like buy_universe is heavy and infrequent, and must not stall a
        strategy's tick. State lives in the job_runs table, so a restart resumes
        the schedule instead of re-firing everything.

        Scans once immediately (so an overdue job fires at boot) then every
        JOB_SCHEDULER_INTERVAL_SECONDS. wait() returns True the instant
        shutdown sets the event, so a day-long interval still stops promptly.
        """
        while True:
            try:
                self._check_jobs()
            except Exception:
                logger.exception("job scheduler scan failed")
            if self._scheduler_stop.wait(
                ServiceSettings.JOB_SCHEDULER_INTERVAL_SECONDS
            ):
                break

    def _check_jobs(self) -> None:
        now = datetime.now(timezone.utc)
        for name, cfg in ServiceSettings.JOBS.items():
            fn = JOB_REGISTRY.get(name)
            if fn is None:
                logger.warning("job %s has no JOB_REGISTRY entry - skipping", name)
                continue
            if self._job_due(name, cfg, now):
                self._run_job(name, fn)

    def _job_due(self, name: str, cfg: dict, now: datetime) -> bool:
        """Due if never run (and run_on_boot_if_stale) or last run is older than
        interval_days."""
        last = self.ctx.db.last_job_run(name)
        if last is None:
            return bool(cfg.get("run_on_boot_if_stale", True))
        ran_at = _parse_ts(last.get("ran_at"))
        if ran_at is None:
            return True
        interval = timedelta(days=cfg.get("interval_days", 14))
        return now - ran_at >= interval

    def _run_job(self, name: str, fn) -> None:
        """Run one job inline on the scheduler thread, recording ok/failed."""
        logger.info("job %s due - running", name)
        try:
            detail = fn(self.ctx)
        except Exception as e:
            logger.exception("job %s failed", name)
            send_discord_message("@here biweekly UNIVERSE job failed")
            self.ctx.db.record_job_run(name, "failed", str(e))

            return
        self.ctx.db.record_job_run(name, "ok", detail)
        logger.info("job %s ok: %s", name, detail)

    def start_strategy(self, name: str) -> bool:
        """Instantiate and start one strategy on its own daemon thread."""
        if name in self.threads and self.threads[name].is_alive():
            logger.warning("strategy %s already running", name)
            return False
        cfg = ServiceSettings.STRATEGIES.get(name)
        if cfg is None:
            logger.warning("strategy %s has no config entry - skipping", name)
            return False
        cls = REGISTRY.get(name)
        if cls is None:
            logger.warning("strategy %s has no REGISTRY entry - skipping", name)
            return False

        strat = cls(self.ctx, cfg["params"])
        thread = threading.Thread(target=strat.run, name=f"strat-{name}", daemon=True)
        thread.start()
        self.strategies[name] = strat
        self.threads[name] = thread
        return True

    def stop_strategy(self, name: str, timeout: float = 10) -> bool:
        """Signal one strategy to stop and join its thread."""
        strat = self.strategies.get(name)
        if strat is None:
            logger.warning("strategy %s not running", name)
            return False
        strat.stop()
        thread = self.threads.get(name)
        if thread is not None:
            thread.join(timeout=timeout)
        self.strategies.pop(name, None)
        self.threads.pop(name, None)
        logger.info("strategy %s stopped", name)
        return True

    def shutdown(self, timeout: float = 10) -> None:
        """Stop all strategies first, then join — one signal before any join."""
        logger.info("shutting down...")
        self._watchdog_stop.set()
        self._scheduler_stop.set()
        for strat in self.strategies.values():
            strat.stop()
        for thread in self.threads.values():
            thread.join(timeout=timeout)
        if self._watchdog_thread is not None:
            self._watchdog_thread.join(timeout=timeout)
            self._watchdog_thread = None
        if self._scheduler_thread is not None:
            self._scheduler_thread.join(timeout=timeout)
            self._scheduler_thread = None
        self.strategies.clear()
        self.threads.clear()

    def status(self) -> dict[str, str]:
        """Map each known strategy to 'running' or 'stopped'."""
        return {
            name: "running" if thread.is_alive() else "stopped"
            for name, thread in self.threads.items()
        }
