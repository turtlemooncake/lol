"""Standalone runner for a single periodic job.

The trading engine stays up only during market hours, so jobs that must run on
their own cadence (e.g. the biweekly weekend universe rebuild) no longer live on
an in-process scheduler thread. Instead an external scheduler (GitHub Actions
cron) invokes this once:

    python run_job.py buy_universe

Cadence + day-of-week now live in the cron schedule, not in code. This runner
keeps the same audit + alerting contract the engine's scheduler had: it records
ok/failed to job_runs and pages Discord on failure, then exits non-zero so the
external scheduler also marks the run red.
"""

import logging
import sys

from config.context import Context
from jobs import JOB_REGISTRY
from services.alpaca_data import AlpacaData
from services.alpaca_trader import AlpacaTrader
from services.discord import send_discord_message
from services.supabase import SupabaseDB

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_job")


def build_job_context() -> Context:
    """Minimal context: jobs use db + Alpaca data/trader, never the gateway."""
    return Context(
        db=SupabaseDB(),
        alpacaData=AlpacaData(),
        alpacaTrader=AlpacaTrader(),
    )


def run_job(name: str) -> int:
    fn = JOB_REGISTRY.get(name)
    if fn is None:
        logger.error("unknown job %r - known jobs: %s", name, ", ".join(JOB_REGISTRY))
        return 2

    ctx = build_job_context()
    logger.info("job %s starting", name)
    try:
        detail = fn(ctx)
    except Exception as e:
        logger.exception("job %s failed", name)
        send_discord_message(f"@here biweekly `{name}` job failed: {e}")
        ctx.db.record_job_run(name, "failed", str(e))
        return 1
    ctx.db.record_job_run(name, "ok", detail)
    logger.info("job %s ok: %s", name, detail)
    return 0


def main() -> None:
    if len(sys.argv) != 2:
        logger.error("usage: python run_job.py <job_name>")
        sys.exit(2)
    sys.exit(run_job(sys.argv[1]))


if __name__ == "__main__":
    main()
