"""Smoke test: generate Excel and PDF reports against a fresh test DB."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.db import ensure_db
from src.ingest import ingest_csv
from src.reports import build_monthly_excel, build_monthly_pdf, build_vendor_pdf

DONATION_CSV = Path(r"C:\Users\info\Downloads\寄附情報一覧(分析用【寄附情報】)_202605251418.csv")
SHIPMENT_CSV = Path(r"C:\Users\info\Downloads\配送情報一覧(分析用【配送情報】)_202605251419.csv")

TEST_DB = PROJECT_ROOT / "data" / "test_reports.duckdb"
OUTPUT_DIR = PROJECT_ROOT / "data" / "reports"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

for p in [TEST_DB, TEST_DB.with_suffix(".duckdb.wal")]:
    if p.exists():
        p.unlink()


def main() -> None:
    conn = ensure_db(TEST_DB)

    print("Ingesting CSVs...")
    for csv in [SHIPMENT_CSV, DONATION_CSV]:
        with open(csv, "rb") as f:
            result = ingest_csv(conn, f, file_name=csv.name)
        print(" ", result.summary())

    print("\nGenerating monthly Excel report (2026年05月)...")
    xlsx = build_monthly_excel(conn, 2026, 5)
    xlsx_path = OUTPUT_DIR / "smoke_monthly_202605.xlsx"
    xlsx_path.write_bytes(xlsx)
    print(f"  Excel: {xlsx_path} ({len(xlsx):,} bytes)")

    print("\nGenerating monthly PDF report (2026年05月)...")
    pdf = build_monthly_pdf(conn, 2026, 5)
    pdf_path = OUTPUT_DIR / "smoke_monthly_202605.pdf"
    pdf_path.write_bytes(pdf)
    print(f"  PDF: {pdf_path} ({len(pdf):,} bytes)")

    # Pick a top vendor for vendor-PDF smoke
    vendor = conn.execute(
        "SELECT vendor FROM shipments GROUP BY vendor ORDER BY SUM(donation_amount) DESC LIMIT 1"
    ).fetchone()[0]
    print(f"\nGenerating vendor PDF for: {vendor}")
    vpdf = build_vendor_pdf(conn, vendor)
    vpdf_path = OUTPUT_DIR / "smoke_vendor.pdf"
    vpdf_path.write_bytes(vpdf)
    print(f"  Vendor PDF: {vpdf_path} ({len(vpdf):,} bytes)")

    conn.close()
    print("\nAll reports generated successfully.")


if __name__ == "__main__":
    main()
