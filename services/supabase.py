import threading
from supabase import create_client
from config.service_settings import ServiceSettings


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
