from datetime import date

from pandas import DataFrame

from src.clients.db_client import SUPABASE_CLIENT


def clear_table(table: str, filter_col: str = "symbol") -> None:
    """Delete all rows from a table."""
    try:
        SUPABASE_CLIENT.table(table).delete().neq(filter_col, "__none__").execute()
        print(f"Success clear_table")
    except Exception as e:
        print(f"Failed to clear_table: {e}")
        return False

    return True


def upsert_rows(
    table: str, rows: list[dict], on_conflict: str = "symbol,snapshot_date"
) -> int:
    if not rows:
        return 0
    BATCH_SIZE = 500
    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]

        try:
            result = (
                SUPABASE_CLIENT.table(table)
                .upsert(batch, on_conflict=on_conflict)
                .execute()
            )
            total += len(result.data) if result.data else 0
        except Exception as e:
            print(f"Failed to upsert_row: {e}")
    return total


def convert_df_to_universe_rows(df: DataFrame) -> list[dict]:
    today = date.today().isoformat()

    rows = (
        df.drop(columns=["close"])
        .reset_index()
        .assign(snapshot_date=today)
        .to_dict(orient="records")
    )

    return rows


def fetch_universe_rows(table: str) -> list[dict]:
    try:

        rows = (
            SUPABASE_CLIENT.table(table)
            .select("*")
            .order("weighted_score", desc=True)
            .execute()
        )
        return rows.data
    except Exception as e:
        print(f"Failed to fetch ${table} rows")

    return []
