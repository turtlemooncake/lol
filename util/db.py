from datetime import date
from pandas import DataFrame


def convert_df_to_universe_rows(df: DataFrame) -> list[dict]:
    today = date.today().isoformat()

    rows = (
        df.drop(columns=["close"])
        .reset_index()
        .assign(snapshot_date=today)
        .to_dict(orient="records")
    )

    return rows
