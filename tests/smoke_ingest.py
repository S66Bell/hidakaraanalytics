"""Smoke test: ingest the two attached CSVs and print DB stats."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.db import ensure_db
from src.ingest import get_import_history, get_table_counts, ingest_csv

DONATION_CSV = Path(r"C:\Users\info\Downloads\寄附情報一覧(分析用【寄附情報】)_202605251418.csv")
SHIPMENT_CSV = Path(r"C:\Users\info\Downloads\配送情報一覧(分析用【配送情報】)_202605251419.csv")

# Use a separate test DB so we don't pollute the real warehouse
TEST_DB = PROJECT_ROOT / "data" / "test_smoke.duckdb"
if TEST_DB.exists():
    TEST_DB.unlink()
wal = TEST_DB.with_suffix(".duckdb.wal")
if wal.exists():
    wal.unlink()


def main() -> None:
    conn = ensure_db(TEST_DB)

    print("=== First ingest ===")
    for csv in [SHIPMENT_CSV, DONATION_CSV]:
        with open(csv, "rb") as f:
            result = ingest_csv(conn, f, file_name=csv.name)
        print(result.summary())

    print("\n=== Counts after first ingest ===")
    print(get_table_counts(conn))

    print("\n=== Second ingest (should all be skipped) ===")
    for csv in [SHIPMENT_CSV, DONATION_CSV]:
        with open(csv, "rb") as f:
            result = ingest_csv(conn, f, file_name=csv.name)
        print(result.summary())

    print("\n=== Counts after second ingest (should be unchanged) ===")
    print(get_table_counts(conn))

    print("\n=== Import history ===")
    print(get_import_history(conn).to_string(index=False))

    print("\n=== Sample shipments ===")
    df = conn.execute(
        """
        SELECT shipment_no, payment_date, vendor, channel,
               donation_amount, product_price,
               (donation_amount - product_price) AS gross_profit,
               category, product_name
        FROM shipments
        ORDER BY shipment_no
        LIMIT 5
        """
    ).fetchdf()
    print(df.to_string(index=False))

    print("\n=== Sample aggregates: monthly KPI ===")
    df = conn.execute(
        """
        SELECT date_trunc('month', payment_date) AS month,
               COUNT(*) AS cnt,
               SUM(donation_amount) AS revenue,
               SUM(donation_amount - product_price) AS gross_profit
        FROM shipments
        GROUP BY 1 ORDER BY 1 DESC
        LIMIT 6
        """
    ).fetchdf()
    print(df.to_string(index=False))

    print("\n=== Sample: top vendors ===")
    df = conn.execute(
        """
        SELECT vendor,
               COUNT(*) AS cnt,
               SUM(donation_amount) AS revenue,
               SUM(donation_amount - product_price) AS gross_profit
        FROM shipments
        GROUP BY vendor
        ORDER BY revenue DESC
        LIMIT 5
        """
    ).fetchdf()
    print(df.to_string(index=False))

    conn.close()
    print(f"\nSmoke test passed. Test DB: {TEST_DB}")


if __name__ == "__main__":
    main()
