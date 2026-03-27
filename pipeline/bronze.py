"""Bronze Layer — Raw Synthea CSV → validated Parquet with metadata.

Reads Synthea CSVs from data/raw/<batch>/csv/, validates schemas,
adds _batch_id + _load_ts metadata, writes Parquet to data/bronze/<table>/.

Supports append-only ingestion: each batch adds new Parquet files
without overwriting previous batches.

Usage:
    python3 pipeline/bronze.py batch_10k
    python3 pipeline/bronze.py batch_10k --validate-only
    python3 pipeline/bronze.py batch_10k --reload-duckdb
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from schemas import SCHEMAS, build_cast_select, get_pk_columns

RAW_DIR = Path("data/raw")
BRONZE_DIR = Path("data/bronze")
DB_PATH = Path("data/clinical.duckdb")


def ingest_table(con, table_name, csv_path, batch_id, bronze_dir, validate_only=False):
    """Ingest one CSV table into the Bronze layer."""
    print(f"  {table_name:<25}", end="", flush=True)

    if not csv_path.exists():
        print("[skip] file not found")
        return None

    cast_select = build_cast_select(table_name)
    load_ts = datetime.now(timezone.utc).isoformat()

    try:
        con.execute(f"DROP VIEW IF EXISTS _raw_{table_name}")
        con.execute(f"""
            CREATE VIEW _raw_{table_name} AS
            SELECT
                {cast_select},
                '{batch_id}' AS _batch_id,
                TIMESTAMPTZ '{load_ts}' AS _load_ts
            FROM read_csv_auto(
                '{csv_path}',
                all_varchar=true,
                null_padding=true,
                ignore_errors=true
            )
        """)

        row_count = con.execute(f"SELECT COUNT(*) FROM _raw_{table_name}").fetchone()[0]
    except Exception as e:
        print(f"[ERROR] {e}")
        return None

    # ── Validation ──
    issues = []
    pk_cols = get_pk_columns(table_name)
    for pk in pk_cols:
        null_count = con.execute(
            f'SELECT COUNT(*) FROM _raw_{table_name} WHERE "{pk}" IS NULL'
        ).fetchone()[0]
        if null_count > 0:
            issues.append(f"    NULL in key '{pk}': {null_count:,} rows")

    if issues:
        print(f"[WARN] {row_count:>12,} rows — {len(issues)} issue(s)")
        for issue in issues:
            print(issue)
    else:
        print(f"[ok]   {row_count:>12,} rows", end="")

    if validate_only:
        print()
        con.execute(f"DROP VIEW IF EXISTS _raw_{table_name}")
        return {"table": table_name, "rows": row_count, "issues": issues}

    # ── Write Parquet ──
    out_dir = bronze_dir / table_name
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{batch_id}.parquet"

    con.execute(f"""
        COPY (SELECT * FROM _raw_{table_name})
        TO '{out_path}' (FORMAT PARQUET, COMPRESSION ZSTD, COMPRESSION_LEVEL 3)
    """)
    con.execute(f"DROP VIEW IF EXISTS _raw_{table_name}")

    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"  → {size_mb:>7.1f} MB")

    return {"table": table_name, "rows": row_count, "size_mb": size_mb, "issues": issues}


def reload_duckdb(bronze_dir):
    """Load all Bronze Parquet files into DuckDB."""
    print(f"\nLoading Bronze → DuckDB ({DB_PATH})...")
    con = duckdb.connect(str(DB_PATH))

    for table_dir in sorted(bronze_dir.iterdir()):
        if not table_dir.is_dir():
            continue
        table_name = table_dir.name
        parquet_files = list(table_dir.glob("*.parquet"))
        if not parquet_files:
            continue

        if len(parquet_files) == 1:
            source = f"'{parquet_files[0]}'"
        else:
            quoted = ", ".join(f"'{f}'" for f in sorted(parquet_files))
            source = f"[{quoted}]"

        con.execute(f"DROP TABLE IF EXISTS {table_name}")
        con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM read_parquet({source})")
        count = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        batches = con.execute(
            f"SELECT COUNT(DISTINCT _batch_id) FROM {table_name}"
        ).fetchone()[0]
        print(f"  {table_name:<25} {count:>12,} rows  ({batches} batch(es))")

    con.close()
    print(f"Database saved to: {DB_PATH}")


def print_summary(results, batch_id):
    """Print ingestion summary."""
    print(f"\n{'=' * 70}")
    print(f"BRONZE INGESTION SUMMARY — batch: {batch_id}")
    print(f"{'=' * 70}")

    total_rows = 0
    total_size = 0.0
    total_issues = 0

    print(f"\n  {'Table':<25} {'Rows':>12} {'Size':>10} {'Status':>8}")
    print(f"  {'─' * 58}")
    for r in results:
        if r is None:
            continue
        total_rows += r["rows"]
        size_str = f"{r.get('size_mb', 0):.1f} MB" if "size_mb" in r else "—"
        total_size += r.get("size_mb", 0)
        n_issues = len(r["issues"])
        total_issues += n_issues
        status = "OK" if n_issues == 0 else f"{n_issues} warn"
        print(f"  {r['table']:<25} {r['rows']:>12,} {size_str:>10} {status:>8}")

    print(f"  {'─' * 58}")
    print(f"  {'TOTAL':<25} {total_rows:>12,} {total_size:>9.1f} MB {total_issues:>7} issues")
    print(f"\n  Output: {BRONZE_DIR}/")


def main():
    parser = argparse.ArgumentParser(description="Bronze layer: Synthea CSV → validated Parquet")
    parser.add_argument("batch", help="Batch folder name under data/raw/ (e.g. batch_10k)")
    parser.add_argument("--validate-only", action="store_true", help="Validate without writing")
    parser.add_argument("--reload-duckdb", action="store_true", help="Also reload DuckDB from Bronze")
    parser.add_argument("--bronze-dir", default=str(BRONZE_DIR), help="Output directory")
    args = parser.parse_args()

    batch_id = args.batch
    csv_dir = RAW_DIR / batch_id / "csv"
    bronze_dir = Path(args.bronze_dir)

    if not csv_dir.exists():
        print(f"CSV directory not found: {csv_dir}")
        sys.exit(1)

    if not args.validate_only:
        bronze_dir.mkdir(parents=True, exist_ok=True)

    print(f"Bronze ingestion: {csv_dir}")
    print(f"Batch ID: {batch_id}")
    print(f"Mode: {'validate-only' if args.validate_only else 'ingest'}\n")

    con = duckdb.connect(":memory:")
    results = []

    for table_name in SCHEMAS:
        csv_path = csv_dir / f"{table_name}.csv"
        result = ingest_table(con, table_name, csv_path, batch_id, bronze_dir, args.validate_only)
        results.append(result)

    con.close()
    print_summary(results, batch_id)

    if args.reload_duckdb and not args.validate_only:
        reload_duckdb(bronze_dir)


if __name__ == "__main__":
    main()
