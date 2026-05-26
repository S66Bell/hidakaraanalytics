"""One-off: ingest 白川村 CSVs into the warehouse for the existing 白川村 municipality."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.db import ensure_db, list_municipalities
from src.ingest import get_counts_per_municipality, ingest_csv


SHIPMENT_CSV = Path(r"C:\Users\info\Downloads\配送情報一覧(実績用データ)_202605252027.csv")
DONATION_CSV = Path(r"C:\Users\info\Downloads\寄附情報一覧(実績用データ)_202605252030.csv")


def main() -> None:
    conn = ensure_db()
    shirakawa = next(m for m in list_municipalities(conn) if m["name"] == "白川村")
    print(f"Target: {shirakawa}")
    print()

    for csv_path in [SHIPMENT_CSV, DONATION_CSV]:
        with open(csv_path, "rb") as f:
            result = ingest_csv(conn, f, shirakawa["id"], file_name=csv_path.name)
        print(result.summary())

    print()
    print("=== Counts per municipality ===")
    print(get_counts_per_municipality(conn).to_string(index=False))
    conn.close()


if __name__ == "__main__":
    main()
