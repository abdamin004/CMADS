"""
Load all Synthea CSV files from data/raw/*/csv/ into DuckDB.
Each CSV becomes a table named after the file (e.g. encounters.csv → encounters).
Run: python pipeline/load_csv_to_duckdb.py
"""

import duckdb
from pathlib import Path

RAW_DIR = Path("data/raw")
DB_PATH = Path("data/clinical.duckdb")

# All 18 Synthea CSV table names
TABLES = [
    "allergies",
    "careplans",
    "claims",
    "claims_transactions",
    "conditions",
    "devices",
    "encounters",
    "imaging_studies",
    "immunizations",
    "medications",
    "observations",
    "organizations",
    "patients",
    "payer_transitions",
    "payers",
    "procedures",
    "providers",
    "supplies",
]


def load_csvs(batch: str | None = None):
    """
    Load CSVs into DuckDB.

    Args:
        batch: specific batch folder name (e.g. 'batch_test').
               If None, loads from all batches found under data/raw/.
    """
    con = duckdb.connect(str(DB_PATH))

    if batch:
        csv_dirs = [RAW_DIR / batch / "csv"]
    else:
        csv_dirs = sorted(RAW_DIR.glob("*/csv"))

    if not csv_dirs:
        print(f"No CSV directories found under {RAW_DIR}")
        return

    for table in TABLES:
        # Collect all matching files across batches
        files = []
        for csv_dir in csv_dirs:
            f = csv_dir / f"{table}.csv"
            if f.exists():
                files.append(str(f))

        if not files:
            print(f"  [skip] {table} — no files found")
            continue

        # Build glob pattern or list for read_csv_auto
        if len(files) == 1:
            source = f"'{files[0]}'"
        else:
            # DuckDB accepts a list of paths
            quoted = ", ".join(f"'{f}'" for f in files)
            source = f"[{quoted}]"

        con.execute(f"DROP TABLE IF EXISTS {table}")
        con.execute(f"""
            CREATE TABLE {table} AS
            SELECT * FROM read_csv_auto({source}, union_by_name=true, null_padding=true, ignore_errors=true)
        """)

        count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  [ok] {table:<25} {count:>10,} rows  ({len(files)} file(s))")

    con.close()
    print(f"\nDatabase saved to: {DB_PATH}")


def show_summary():
    con = duckdb.connect(str(DB_PATH), read_only=True)
    print("\n=== Tables in clinical.duckdb ===")
    tables = con.execute("SHOW TABLES").fetchall()
    for (t,) in tables:
        count = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:<25} {count:>10,} rows")
    con.close()


if __name__ == "__main__":
    import sys

    batch_arg = sys.argv[1] if len(sys.argv) > 1 else None
    if batch_arg:
        print(f"Loading batch: {batch_arg}")
    else:
        print("Loading all batches...")

    load_csvs(batch=batch_arg)
    show_summary()
