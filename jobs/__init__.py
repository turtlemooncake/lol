from jobs.buy_universe import build_universe

# Maps a JOBS config name -> callable(ctx) -> detail string. The engine's
# scheduler looks jobs up here, the same way strategies/REGISTRY works.
JOB_REGISTRY = {
    "buy_universe": build_universe,
}
