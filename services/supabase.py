import threading
from datetime import datetime, timezone

from supabase import create_client
from config.service_settings import ServiceSettings

HEARTBEATS_TABLE = "heartbeats"
JOB_RUNS_TABLE = "job_runs"


class SupabaseDB:
    def __init__(self, client="supabase"):
        self._lock = threading.Lock()  # todo: remove if unused
        self._DB_CLIENT = (
            create_client(ServiceSettings.SUPABASE_URL, ServiceSettings.SUPABASE_KEY)
            if client == "supabase"
            else None
        )

    def clear_table(self, table: str, filter_col: str = "symbol") -> bool:
        """Delete all rows from a table."""
        try:
            self._DB_CLIENT.table(table).delete().neq(filter_col, "__none__").execute()
            print(f"Success clear_table")
        except Exception as e:
            print(f"Failed to clear_table: {e}")
            return False

        return True

    def upsert_rows(
        self, table: str, rows: list[dict], on_conflict: str = "symbol,snapshot_date"
    ) -> int:
        """Insert rows"""
        if not rows:
            return 0
        BATCH_SIZE = 500
        total = 0
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i : i + BATCH_SIZE]

            try:
                result = (
                    self._DB_CLIENT.table(table)
                    .upsert(batch, on_conflict=on_conflict)
                    .execute()
                )
                total += len(result.data) if result.data else 0
            except Exception as e:
                print(f"Failed to upsert_row: {e}")
        return total

    # def insert_row(self, table: str, row: dict) -> dict | None:
    #     """Insert a single row; returns the inserted row (or None on failure)."""
    #     try:
    #         result = self._DB_CLIENT.table(table).insert(row).execute()
    #         return result.data[0] if result.data else None
    #     except Exception as e:
    #         print(f"Failed to insert_row into {table}: {e}")
    #         return None

    # def update_row(self, table: str, match: dict, values: dict) -> bool:
    #     """Update rows in `table` matching every col=val in `match`."""
    #     try:
    #         query = self._DB_CLIENT.table(table).update(values)
    #         for col, val in match.items():
    #             query = query.eq(col, val)
    #         query.execute()
    #         return True
    #     except Exception as e:
    #         print(f"Failed to update_row in {table}: {e}")
    #         return False

    def beat(self, name: str, status: str = "running") -> None:
        """Refresh a strategy's heartbeat: one row per name, upserted each loop.

        The watchdog reads beat_at to spot a thread that's alive but wedged.
        Fail-soft: a DB hiccup must never take down a strategy's loop, so we
        only log on failure.
        """
        row = {
            "name": name,
            "status": status,
            "beat_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self._DB_CLIENT.table(HEARTBEATS_TABLE).upsert(
                row, on_conflict="name"
            ).execute()
        except Exception as e:
            print(f"Failed to beat for {name}: {e}")

    def fetch_heartbeats(self) -> list[dict]:
        """All heartbeat rows (name, status, beat_at) for the watchdog."""
        try:
            rows = self._DB_CLIENT.table(HEARTBEATS_TABLE).select("*").execute()
            return rows.data
        except Exception as e:
            print(f"Failed to fetch heartbeats: {e}")
            return []

    def record_job_run(self, name: str, status: str, detail: str | None = None) -> None:
        """Append one row to the job_runs log after a scheduled job finishes.

        The scheduler writes ran_at itself (UTC) so the due-math compares two
        clocks on the same machine, never app-vs-DB. Fail-soft: a DB hiccup here
        only logs -- the worst case is the job re-runs sooner than intended.
        """
        row = {
            "name": name,
            "status": status,
            "detail": detail,
            "ran_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self._DB_CLIENT.table(JOB_RUNS_TABLE).insert(row).execute()
        except Exception as e:
            print(f"Failed to record_job_run for {name}: {e}")

    def last_job_run(self, name: str) -> dict | None:
        """The most recent job_runs row for `name` (or None if never run).

        The scheduler reads only ran_at off this to decide due-ness. Returns
        None on a DB error as well, which the scheduler treats the same as
        "never run" -- worst case a transient error fires the job once early.
        """
        try:
            rows = (
                self._DB_CLIENT.table(JOB_RUNS_TABLE)
                .select("*")
                .eq("name", name)
                .order("ran_at", desc=True)
                .limit(1)
                .execute()
            )
            return rows.data[0] if rows.data else None
        except Exception as e:
            print(f"Failed to fetch last_job_run for {name}: {e}")
            return None

    def fetch_rows(self, table, order="weighted_score") -> list[dict]:
        """Fetch rows"""
        try:
            rows = (
                self._DB_CLIENT.table(table)
                .select("*")
                .order(order, desc=True)
                .execute()
            )
            return rows.data
        except Exception as e:
            print(f"Failed to fetch ${table} rows")

        return []
